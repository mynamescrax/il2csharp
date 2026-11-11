from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.runtime.eh import _EhMixin
from il2cpp.runtime.fields import _FieldsMixin
from il2cpp.runtime.registration import _RegistrationMixin
from il2cpp.runtime.types import _TypesMixin



class Il2Cpp(_RegistrationMixin, _TypesMixin, _FieldsMixin, _EhMixin):
    """Runtime/metadata facade: registrations, type names, fields, EH tables.

    Split across il2cpp/runtime/ purely for file size.  The memo caches
    (_chain_cache, _bases_cache, ...) stay per-instance, set in __init__.
    """
