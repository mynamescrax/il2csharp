// Single-unit Roslyn diagnostic only. Use when recovered mscorlib supplies
// System.Attribute but its compiler-only IndexerNameAttribute was stripped.
// The host SDK's marker derives from the host Attribute, a different type.
namespace System.Runtime.CompilerServices
{
    internal sealed class IndexerNameAttribute : global::System.Attribute
    {
        public IndexerNameAttribute(string indexerName) { }
    }
}
