using System;
struct Vector { public float x, y, z; }
struct Hit { public Vector point { get; set; } }
static class Program
{
    static int loopSource, loopRefills, loopTicks;
    static float SqrtFloat(float value) => (float)Math.Sqrt(value);
    static double SqrtDouble(double value) => Math.Sqrt(value);
    static int Refill()
    {
        loopRefills++;
        if (loopRefills == 1) return loopSource = 2;
        return 0;
    }
    static void Tick()
    {
        if (++loopTicks > 10) throw new Exception("loop header value was frozen");
        loopSource--;
    }
    static void HeaderLoop()
    {
        loopSource = loopRefills = loopTicks = 0;
        while (true)
{
var t0 = loopSource;
if (!(t0 != 0))
{
t0 = Refill();
}
if (t0 == 0)
{
break;
}
Tick();
}
        if (loopRefills != 2 || loopTicks != 2 || loopSource != 0)
            throw new Exception("loop header/refill execution order");
    }
    static Vector Point(Hit s_20)
    {
        Vector s_40 = default;
        s_40 = s_20.point;
        return s_40;
    }
    static void Arrays()
    {
        var t0 = new string[2];
t0[0x0] = "left";
t0[0x1] = "right";
var t1 = new string[2];
        if (string.Concat(t0) != "leftright")
            throw new Exception("array identity / stores");
        if (ReferenceEquals(t0, t1))
            throw new Exception("distinct allocations collapsed");
    }
    static void Main()
    {
        HeaderLoop();
        Arrays();
        var p = Point(new Hit { point = new Vector { x = 3, y = 4, z = 5 } });
        if (p.x != 3 || p.y != 4 || p.z != 5) throw new Exception("sret receiver");
        foreach (float x in new[] { 0f, -0f, 1f, 2f, 4f, 9f, float.Epsilon,
                                    float.MaxValue, float.PositiveInfinity })
            if (BitConverter.SingleToInt32Bits(SqrtFloat(x)) !=
                BitConverter.SingleToInt32Bits(MathF.Sqrt(x)))
                throw new Exception("float sqrt: " + x);
        if (!float.IsNaN(SqrtFloat(-1)) || !float.IsNaN(SqrtFloat(float.NaN)))
            throw new Exception("float sqrt NaN");
        if (SqrtDouble(9) != 3 || !double.IsNaN(SqrtDouble(-1)) ||
            !double.IsPositiveInfinity(SqrtDouble(double.PositiveInfinity)))
            throw new Exception("double sqrt");
        Console.WriteLine("PASS: loop header, allocation identity, GC-store twins, sret receiver, scalar sqrt");
    }
}
