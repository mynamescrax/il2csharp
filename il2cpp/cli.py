from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.arm64 import is_arm64_binary
from il2cpp.binary import ELF, load_binary
from il2cpp.emitter import Emitter
from il2cpp.headers import HeaderEmitter
from il2cpp.metadata import Metadata
from il2cpp.runtime.core import Il2Cpp

def find_game_files(path=None, *, metadata=None, binary=None):
    """Discover one unambiguous pair; explicit files always take priority.

    Directory targets are a boundary: never pair them with a parent game's
    binary. Direct metadata files may use the standard Unity ancestor layout.
    Discovery reads directories only and never executes the native binary.
    """
    def explicit(value, label):
        if value is None:
            return None
        value = os.path.abspath(os.fspath(value))
        if not os.path.isfile(value):
            raise ValueError('%s file does not exist: %s' % (label, value))
        return value

    def pick(paths, label, flag):
        paths = sorted(set(paths))
        if len(paths) > 1:
            raise ValueError('multiple %s files found; select one with %s: %s' % (
                label, flag, ', '.join(paths)))
        return paths[0] if paths else None

    def scan(root, names):
        found = []
        for directory, dirs, files in os.walk(root):
            dirs.sort()
            for name in sorted(files):
                if name.casefold() in names:
                    found.append(os.path.join(directory, name))
        return found

    gmd, bp = explicit(metadata, 'metadata'), explicit(binary, 'binary')
    root = None
    if path is not None:
        target = os.path.abspath(os.fspath(path))
        if os.path.isdir(target):
            root = target
        elif os.path.isfile(target):
            if os.path.basename(target).casefold() == 'global-metadata.dat' or target == gmd:
                gmd = gmd or target
            else:
                bp = bp or target
        elif not (gmd or bp):
            return None, None
    if gmd and bp:
        return gmd, bp
    if root is None:
        root = os.path.dirname(bp or gmd) if bp or gmd else None
        if root and gmd and not bp:
            # .../<Game>_Data/il2cpp_data/Metadata/global-metadata.dat
            parent = os.path.dirname(root)
            data_dir = os.path.dirname(parent)
            if os.path.basename(root).casefold() == 'metadata' and \
                    os.path.basename(parent).casefold() == 'il2cpp_data' and \
                    os.path.basename(data_dir).casefold().endswith('_data'):
                root = os.path.dirname(data_dir)
    if root is None:
        return gmd, bp
    if gmd is None:
        gmd = pick(scan(root, {'global-metadata.dat'}), 'metadata', '--metadata')
    if bp is None:
        bp = pick(scan(root, {'gameassembly.dll', 'libil2cpp.so'}), 'binary', '--binary')
    return gmd, bp


# -- assembly emission ---------------------------------------------------

_W = {}


def _load_runtime(gmd, bp, verbose):
    """Read metadata + binary and resolve every method's native address.

    Mirrors the phase `main` runs before the image loop, factored out
    because a parallel build repeats it once per worker process. It keeps
    that phase whole: a worker that loaded less than the serial build would
    silently emit fewer bodies.
    """
    meta = Metadata(gmd)
    bin_ = load_binary(bp)
    if bin_ is None:
        raise ValueError('unsupported binary format')
    il = Il2Cpp(meta, bin_)
    il.verbose = verbose
    il.assign_images()
    try:
        il.find_registrations()
    except RuntimeError:
        # The Android loader assumes a different registration struct shape
        # and lands on a silently wrong registration for a PE; same gate as
        # `main`.
        if not isinstance(bin_, ELF):
            raise
        il.find_registrations_android()
    il.load_function_bounds()
    il.resolve_method_addrs()
    il._mod_ptr_cache.clear()  # free raw pointer arrays
    return meta, il


def _worker_init(gmd, bp, out_dir, asm_comments, with_bodies, max_methods,
                 verbose, type_filter, publicize=False, raw_addr=False):
    """One runtime and one Emitter per worker process, reused for every
    image that process is handed (the load costs ~4 s, an image ~12 s)."""
    meta, il = _load_runtime(gmd, bp, verbose)
    _W['meta'] = meta
    _W['em'] = Emitter(il, out_dir, asm_comments=asm_comments,
                       with_bodies=with_bodies, max_methods=max_methods,
                       verbose=verbose, type_filter=type_filter,
                       publicize=publicize, raw_addr=raw_addr)


def _worker_emit(image_name):
    """Emit one image and report per-image deltas.

    Deltas, not totals: the parent's running totals are then the serial
    ones, so `--workers N` prints the same log as `--workers 1`.
    """
    em, meta = _W['em'], _W['meta']
    img = next((i for i in meta.images if i.name == image_name), None)
    if img is None:
        return {'files': 0, 'lifted': 0, 'failed': 0, 'fallbacks': 0,
                'emit_failed': 0, 'lifter': em.lifter is not None,
                'error': 'image not found in metadata'}
    before = (em.lifted, em.failed, em.fallbacks, em.emit_failed)
    error = None
    try:
        files = em.write_assembly_split(img)
    except Exception as ex:
        files, error = 0, '%s: %s' % (type(ex).__name__, ex)
    after = (em.lifted, em.failed, em.fallbacks, em.emit_failed)
    return {'files': files, 'lifted': after[0] - before[0],
            'failed': after[1] - before[1],
            'fallbacks': after[2] - before[2],
            'emit_failed': after[3] - before[3],
            'lifter': em.lifter is not None, 'error': error}


def _auto_workers():
    """Default width for `--workers 0`: half the cores, never more than 8.

    Both reasons are real. Memory: a worker holding a live runtime sits at
    423 MB resident after the load and 581 MB after the four heaviest
    assemblies, peaking at 672-783 MB, so twelve workers is ~8 GB of peak
    working set -- enough to die beside anything else running, which is
    what a 12-worker run did here. Politeness: a promotion build is not
    the only thing on the machine, and taking every core starves whatever
    else is running. An explicit `--workers N` still overrides this.
    """
    return max(1, min(8, (os.cpu_count() or 2) // 2))


def _worker_count(args, images):
    """Resolve --workers, declining the combinations that cannot hold."""
    if args.workers < 0:
        return 0, '--workers must be >= 0'
    workers = args.workers if args.workers else _auto_workers()
    if len(images) < 2 or workers < 2:
        return 1, None
    if args.max_methods is not None:
        # the cap is a whole-build brake; a per-worker cap would lift up
        # to N times the bodies that were asked for
        return 1, '--max-methods is a per-build cap; running --workers 1'
    if getattr(args, 'bodies', None):
        # --bodies is written by the parent's own Emitter; worker bodies
        # live in another process, so a pool would write the empty dict.
        return 1, '--bodies is collected parent-side; running --workers 1'
    return workers, None


def _weighted_order(images, meta):
    """Submission order for the pool: heaviest image first.

    The executor hands queued work to workers in submission order, so the
    image submitted last sets the tail. Counting native methods per image
    (`MethodDef.image` is filled by the parent's `assign_images`) is the
    cheap predictor of emit cost; ties keep metadata order because the
    sort is stable, and a caller without a metadata table gets that order
    unchanged.
    """
    if meta is None or not images:
        return list(images)
    try:
        counts = {}
        for m in meta.methods:
            if m.addr and m.image >= 0:
                counts[m.image] = counts.get(m.image, 0) + 1
        index = {img.name: i for i, img in enumerate(meta.images)}
        return sorted(images,
                      key=lambda img: -counts.get(index.get(img.name, -1), 0))
    except (AttributeError, TypeError):
        return list(images)


# Chunked pool: a worker is handed a contiguous slice of one image's file
# plan, so one huge image no longer sets the wall. ~16 slices per worker over
# the whole build keeps the tail near one slice, and the floor keeps tiny
# builds from becoming one job per type.
_CHUNKS_PER_WORKER = 16
_MIN_CHUNK_WEIGHT = 25


def _chunk_ranges(weights, target):
    """Contiguous `(lo, hi)` ranges over `weights`, in order, covering every
    index once. A range closes as soon as its weight reaches `target`, so a
    single heavy item is its own range and never splits; the last range is
    whatever is left."""
    out = []
    lo = 0
    acc = 0
    for i, w in enumerate(weights):
        acc += w
        if acc >= target:
            out.append((lo, i + 1))
            lo = i + 1
            acc = 0
    if lo < len(weights):
        out.append((lo, len(weights)))
    return out


def _worker_emit_chunk(image_name, lo, hi, expect):
    """Emit files `lo..hi` of one image's plan; report deltas and products.

    The plan is recomputed here (it is a pure function of the metadata) and
    must match the parent's length, or the slice would name different files.
    Returns the per-image products the parent needs for the tail: the
    `sub_<va>` VAs this slice referenced and whether `--raw-addr` fired.
    """
    em, meta = _W['em'], _W['meta']
    res = {'files': 0, 'lifted': 0, 'failed': 0, 'fallbacks': 0,
           'emit_failed': 0, 'subs': [], 'raw': False,
           'lifter': em.lifter is not None, 'error': None}
    img = next((i for i in meta.images if i.name == image_name), None)
    if img is None:
        res['error'] = 'image not found in metadata'
        return res
    plans = _W.setdefault('plans', {})
    plan = plans.get(image_name)
    if plan is None:
        plan = plans[image_name] = em._plan_top_files(img)
    if len(plan) != expect:
        res['error'] = 'file plan mismatch: worker %d files, parent %d' % (
            len(plan), expect)
        return res
    before = (em.lifted, em.failed, em.fallbacks, em.emit_failed)
    subs = set()
    raw_any = False
    try:
        for td, base in plan[lo:hi]:
            s, raw = em._emit_one_top(td, img, base)
            subs |= s
            raw_any = raw_any or raw
            res['files'] += 1
    except Exception as ex:
        res['error'] = '%s: %s' % (type(ex).__name__, ex)
    after = (em.lifted, em.failed, em.fallbacks, em.emit_failed)
    res['lifted'] = after[0] - before[0]
    res['failed'] = after[1] - before[1]
    res['fallbacks'] = after[2] - before[2]
    res['emit_failed'] = after[3] - before[3]
    res['subs'] = sorted(subs)
    res['raw'] = raw_any
    return res


def _emit_pool_by_chunk(images, em, args, gmd, bp, workers, quiet, t0):
    """Slices of every image across worker processes.

    Per-file emission reads nothing another file wrote; the three products
    that live outside a type file (the `sub_<va>` stub class, the
    `--raw-addr` helper, the .csproj) are written once per image here, in
    the parent, from the union of what the slices return. Counters are
    summed per image in metadata order, so the log matches the serial one.
    """
    from concurrent.futures import ProcessPoolExecutor
    initargs = (gmd, bp, args.out, args.asm, not args.decls_only,
                args.max_methods, args.verbose, args.types,
                getattr(args, 'publicize', False),
                getattr(args, 'raw_addr', False))
    plans = {}
    total_w = 0
    for img in images:
        plan = em._plan_top_files(img)
        ws = [em._top_weight(td) for td, _base in plan]
        plans[img.name] = (plan, ws)
        total_w += sum(ws)
    target = max(_MIN_CHUNK_WEIGHT, total_w // (workers * _CHUNKS_PER_WORKER))
    jobs = []
    ranges = {}
    for idx, img in enumerate(images):
        plan, ws = plans[img.name]
        ranges[img.name] = _chunk_ranges(ws, target)
        for k, (lo, hi) in enumerate(ranges[img.name]):
            jobs.append((-sum(ws[lo:hi]), idx, k, img.name, lo, hi, len(plan)))
    jobs.sort()         # heaviest slice first; ties keep image/slice order
    if not quiet:
        print('workers: %d processes | %d images | %d slices' % (
            workers, len(images), len(jobs)), flush=True)
    total = {'files': 0, 'lifted': 0, 'failed': 0, 'fallbacks': 0,
             'emit_failed': 0, 'lifter': True, 'errors': []}
    with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init,
                             initargs=initargs) as pool:
        futures = {(name, k): pool.submit(_worker_emit_chunk, name, lo, hi, n)
                   for (_w, _idx, k, name, lo, hi, n) in jobs}
        for img in images:          # report in metadata order, like serial
            files = lifted = failed = fallbacks = emit_failed = 0
            subs = set()
            raw_any = False
            error = None
            for k in range(len(ranges[img.name])):
                try:
                    r = futures[(img.name, k)].result()
                except Exception as ex:
                    error = error or '%s: %s' % (type(ex).__name__, ex)
                    continue
                error = error or r['error']
                files += r['files']
                lifted += r['lifted']
                failed += r['failed']
                fallbacks += r['fallbacks']
                emit_failed += r['emit_failed']
                subs.update(r['subs'])
                raw_any = raw_any or r['raw']
                total['lifter'] = total['lifter'] and r['lifter']
            if error is None:
                try:
                    files += em.write_assembly_tail(img, subs, raw_any)
                except Exception as ex:
                    error = '%s: %s' % (type(ex).__name__, ex)
            if error:
                total['errors'].append('%s: %s' % (img.name, error))
            total['files'] += files
            total['lifted'] += lifted
            total['failed'] += failed
            total['fallbacks'] += fallbacks
            total['emit_failed'] += emit_failed
            if not quiet:
                print('  %-52s %5d types  (%d bodies, %d failed)' % (
                    img.name, files, total['lifted'], total['failed']),
                    flush=True)
    if not quiet:
        print('workers: %d processes | wall %d ms' % (workers, time_ms() - t0),
              flush=True)
    return total


def _emit_pool_by_image(images, em, args, gmd, bp, workers, quiet, t0):
    """Whole images across worker processes (heaviest image first).

    The pre-chunking schedule, kept for an emitter that cannot plan its
    files (no `_plan_top_files`); the Emitter itself takes the chunked
    path below."""
    from concurrent.futures import ProcessPoolExecutor
    initargs = (gmd, bp, args.out, args.asm, not args.decls_only,
                args.max_methods, args.verbose, args.types,
                getattr(args, 'publicize', False),
                getattr(args, 'raw_addr', False))
    # say the width before the pool exists: a run killed part-way (a machine
    # under memory pressure will kill the parent, not a worker) otherwise
    # leaves a log that never mentions how wide it got
    if not quiet:
        print('workers: %d processes | %d images' % (workers, len(images)),
              flush=True)
    total = {'files': 0, 'lifted': 0, 'failed': 0, 'fallbacks': 0,
             'emit_failed': 0, 'lifter': True, 'errors': []}
    # heaviest first: the tail is the last image handed to a worker
    scheduled = _weighted_order(images, getattr(em, 'meta', None))
    with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init,
                             initargs=initargs) as pool:
        futures = {img.name: pool.submit(_worker_emit, img.name)
                   for img in scheduled}
        for img in images:          # report in metadata order, like serial
            r = futures[img.name].result()
            if r['error']:
                total['errors'].append('%s: %s' % (img.name, r['error']))
            total['files'] += r['files']
            total['lifted'] += r['lifted']
            total['failed'] += r['failed']
            total['fallbacks'] += r['fallbacks']
            total['emit_failed'] += r['emit_failed']
            total['lifter'] = total['lifter'] and r['lifter']
            if not quiet:
                print('  %-52s %5d types  (%d bodies, %d failed)' % (
                    img.name, r['files'], total['lifted'], total['failed']),
                    flush=True)
    if not quiet:
        print('workers: %d processes | wall %d ms' % (workers, time_ms() - t0),
              flush=True)
    return total


def _emit_assemblies(images, em, args, gmd, bp):
    """Emit every image, serially or across worker processes.

    An image owns its output directory, its `__SharedBodyStubs.cs` and its
    `.csproj`, and reads nothing another image wrote, so the tree does not
    depend on the schedule. Returns the serial counters either way.
    """
    quiet = getattr(args, 'quiet', False)
    workers, note = _worker_count(args, images)
    if note and not quiet:
        print('note: ' + note)
    t0 = time_ms()
    if workers < 1:
        workers = 1
    if workers == 1:
        total_files = 0
        for img in images:
            n = em.write_assembly_split(img)
            total_files += n
            if not quiet:
                print('  %-52s %5d types  (%d bodies, %d failed)' % (
                    img.name, n, em.lifted, em.failed), flush=True)
        return {'files': total_files, 'lifted': em.lifted,
                'failed': em.failed, 'fallbacks': em.fallbacks,
                'emit_failed': em.emit_failed, 'lifter': em.lifter is not None,
                'errors': []}
    if hasattr(em, '_plan_top_files'):
        return _emit_pool_by_chunk(images, em, args, gmd, bp, workers, quiet, t0)
    return _emit_pool_by_image(images, em, args, gmd, bp, workers, quiet, t0)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(
        prog='il2csharp',
        description='IL2CPP -> C# recovery with real (lifted) method bodies.')
    ap.add_argument('target', nargs='?', help='game dir, metadata file, or binary file')
    ap.add_argument('--metadata', help='explicit global-metadata.dat path (renamed files supported)')
    ap.add_argument('--binary', help='explicit GameAssembly.dll / libil2cpp.so path')
    ap.add_argument('-o', '--out', default='il2csharp_out', help='output directory')
    ap.add_argument('--only', default=None, help='comma-separated assembly name filters (substring match)')
    ap.add_argument('--types', default=None, help='case-insensitive full type-name substring; nested matches retain the owner file')
    ap.add_argument('--strict', action='store_true', help='return nonzero on body-lifting fallback or missing backend')
    ap.add_argument('--decls-only', action='store_true', help='skip method body lifting')
    ap.add_argument('--asm', action='store_true', help='include native asm comments in bodies')
    ap.add_argument('--publicize', action='store_true',
                    help='emit every declaration public (recompilation aid: bodies read '
                         'private/internal members the way native code does)')
    ap.add_argument('--raw-addr', action='store_true',
                    help='route every `(byte*)E` raw-access base through a declared '
                         '`__addr(E)` helper (recompilation aid: managed bases throw '
                         'instead of failing CS0030)')
    ap.add_argument('--max-methods', type=int, default=None, help='cap lifted bodies (debug)')
    ap.add_argument('--workers', type=int, default=1,
                    help='emit assemblies in N worker processes (0 = auto: half the cores, '
                         'max 8). The tree is byte-identical to --workers 1; only the schedule '
                         'changes')
    ap.add_argument('--probe', action='store_true', help='diagnostics only')
    ap.add_argument('--emit-h', action='store_true',
                    help='also emit an il2cpp.h-style C header (Il2CppDumper format)')
    ap.add_argument('-v', '--verbose', action='store_true')
    ap.add_argument('-q', '--quiet', action='store_true',
                    help='suppress progress; still prints errors and --json')
    ap.add_argument('--json', action='store_true',
                    help='print a one-line JSON summary on stdout')
    ap.add_argument('--manifest', metavar='FILE',
                    help='write the same JSON summary to FILE')
    ap.add_argument('--bodies', nargs='?', const='bodies.json', metavar='FILE',
                    help='write address-keyed C# bodies for Sunshine --rival '
                         '(default: <out>/bodies.json)')
    args = ap.parse_args(argv[1:])

    if args.max_methods is not None and args.max_methods < 0:
        ap.error('--max-methods must be nonnegative')
    if args.workers < 0:
        ap.error('--workers must be >= 0 (0 picks half the cores, max 8)')
    if not args.target and not (args.metadata and args.binary):
        ap.error('provide a target or both --metadata and --binary')
    try:
        gmd, bp = find_game_files(args.target, metadata=args.metadata, binary=args.binary)
    except (OSError, ValueError) as ex:
        print('error:', ex)
        return 1
    if not gmd:
        print('error: could not locate global-metadata.dat under', args.target)
        return 1
    def say(*parts):
        if not args.quiet:
            print(*parts)
    say('metadata:', gmd)
    say('binary  :', bp)
    try:
        meta = Metadata(gmd)
    except (OSError, ValueError, struct.error) as ex:
        print('error: could not read metadata:', ex)
        return 1
    say('metadata v%d | %d types | %d methods | %d images | %d string literals' % (
        meta.version, len(meta.typedefs), len(meta.methods), len(meta.images),
        len(meta.string_literals)))
    if not bp:
        print('error: no binary found (need GameAssembly.dll / libil2cpp.so)')
        return 1
    try:
        bin_ = load_binary(bp)
    except (OSError, ValueError, struct.error) as ex:
        print('error: could not read binary:', ex)
        return 1
    if bin_ is None:
        print('error: unsupported binary format')
        return 1
    say('binary loaded: %d sections, %d exports%s' % (len(bin_.sections), len(bin_.exports), (' | relocs: %d' % bin_.reloc_applied) if getattr(bin_, 'reloc_applied', 0) else ''))
    il = Il2Cpp(meta, bin_)
    il.verbose = args.verbose
    t0 = time_ms()
    try:
        il.assign_images()
        try:
            il.find_registrations()
        except RuntimeError:
            # The Android loader assumes a different registration struct
            # shape. Probed on the x64 PE it does not fail: it lands on a
            # code_reg_va 0x10 off the classic answer with the same module
            # count and the same resolved method coverage, so trying it on
            # a PE trades a clean error for a silently wrong registration.
            if not isinstance(bin_, ELF):
                raise
            il.find_registrations_android()
        il.load_function_bounds()
        il.resolve_method_addrs()
    except (OSError, ValueError, IndexError, KeyError, struct.error,
            RuntimeError) as ex:
        print('error: could not read code/metadata registrations:', ex)
        return 1
    getattr(il, '_mod_ptr_cache', {}).clear()  # free raw pointer arrays
    n_addr = sum(1 for m in meta.methods if m.addr)
    say('registrations ok | %d/%d methods have native code | %d ms' % (
        n_addr, len(meta.methods), time_ms() - t0))

    if args.probe:
        for name, mod in sorted(il.modules.items()):
            print('  %-50s methods=%d' % (name, mod.method_pointer_count))
        return 0

    if not args.decls_only:
        if is_arm64_binary(bin_) and not HAVE_CAPSTONE:
            say('warning: Capstone not installed; ARM64 bodies disabled (pip install capstone)')
        elif not is_arm64_binary(bin_) and not HAVE_ICED:
            say('warning: iced-x86 not installed; x64 bodies disabled (pip install iced-x86)')

    only = [t.strip().lower() for t in args.only.split(',')] if args.only else None
    images = [img for img in meta.images
              if not only or any(t in img.name.lower() for t in only)]
    if only and not images:
        print('error: --only matched no assembly:', args.only)
        return 1

    os.makedirs(args.out, exist_ok=True)
    if args.emit_h:
        t0 = time_ms()
        hpath = os.path.join(args.out, 'il2cpp.h')
        n_types = HeaderEmitter(il, hpath).write()
        say('il2cpp.h: %d types in %d ms -> %s' % (n_types, time_ms() - t0, hpath))
    workers, _note = _worker_count(args, images)
    # the parent keeps an Emitter for the two whole-tree files; with a pool
    # running it needs no Lifter of its own
    em = Emitter(il, args.out, asm_comments=args.asm,
                 with_bodies=not args.decls_only and workers == 1,
                 max_methods=args.max_methods, verbose=args.verbose,
                 type_filter=args.types, publicize=args.publicize,
                 raw_addr=args.raw_addr)
    t0 = time_ms()
    stats = _emit_assemblies(images, em, args, gmd, bp)
    em.write_script_json(os.path.join(args.out, 'script.json'))
    em.write_string_literals(os.path.join(args.out, 'stringliteral.json'))
    for err in stats['errors']:
        print('error:', err)
    bodies_path = None
    if args.bodies:
        bodies_path = args.bodies if os.path.isabs(args.bodies) else os.path.join(args.out, args.bodies)
        parent = os.path.dirname(os.path.abspath(bodies_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        em.write_bodies(bodies_path)
        say('bodies: %d -> %s' % (len(em.bodies), bodies_path))
    elapsed = time_ms() - t0
    summary = {
        'out': os.path.abspath(args.out),
        'files': stats['files'],
        'lifted': stats['lifted'],
        'failed': stats['failed'],
        'fallbacks': stats['fallbacks'],
        'emit_failed': stats['emit_failed'],
        'ms': elapsed,
        'bodies': os.path.abspath(bodies_path) if bodies_path else None,
    }
    if args.manifest:
        import json
        os.makedirs(os.path.dirname(os.path.abspath(args.manifest)) or '.', exist_ok=True)
        with open(args.manifest, 'w', encoding='utf-8') as fh:
            json.dump(summary, fh, indent=1)
        say('manifest:', os.path.abspath(args.manifest))
    say('done: %d type files in %d ms | bodies lifted: %d, failed: %d | '
        'structured fallbacks: %d, type emit failures: %d' % (
        stats['files'], elapsed, stats['lifted'], stats['failed'],
        stats['fallbacks'], stats['emit_failed']))
    if args.json:
        import json
        print(json.dumps(summary, separators=(',', ':')))
    failed = bool(stats['failed'] or stats['emit_failed'] or stats['errors'])
    if args.strict and not args.decls_only:
        failed = failed or bool(stats['fallbacks']) or not stats['lifter']
    return 1 if failed else 0


def time_ms():
    import time
    return int(time.time() * 1000)

if __name__ == '__main__':
    sys.exit(main(sys.argv))
