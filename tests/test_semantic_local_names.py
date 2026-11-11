"""Final-render readability for concretely typed object-family locals."""
from types import SimpleNamespace

from il2cpp import Decompiler


def decompiler():
    return object.__new__(Decompiler)


def test_concrete_obj_locals_get_type_derived_names_but_unknown_object_stays():
    lines = [
        "GameObject obj1 = new GameObject();",
        "obj1.SetActive(true);",
        "System.Type obj2 = typeof(GameObject);",
        "string obj3 = \"obj1 and obj2 stay literal\";",
        "// obj3 stays unchanged in this comment",
        "object obj4 = obj5() /*indirect*/(obj1);",
        "foreach (Transform obj6 in obj7)",
        "{",
        "    obj6.position = obj1.transform.position;",
        "}",
    ]

    assert decompiler()._semantic_local_names(lines) == [
        "GameObject gameObject1 = new GameObject();",
        "gameObject1.SetActive(true);",
        "System.Type type1 = typeof(GameObject);",
        "string text1 = \"obj1 and obj2 stay literal\";",
        "// obj3 stays unchanged in this comment",
        "object obj4 = obj5() /*indirect*/(gameObject1);",
        "foreach (Transform transform1 in obj7)",
        "{",
        "    transform1.position = gameObject1.transform.position;",
        "}",
    ]


def test_semantic_prefixes_cover_arrays_pointers_generics_and_acronyms():
    lines = [
        "byte[] obj1 = new byte[4];",
        "SimulationMessage* obj2 = unknown;",
        "IAsyncResult obj3 = task;",
        "List<int> obj4 = new List<int>();",
        "T obj5 = default;",
        "RTHandle obj6 = handle;",
        "TMP_CharacterInfo[] obj7 = info;",
    ]

    assert decompiler()._semantic_local_names(lines) == [
        "byte[] byteArray1 = new byte[4];",
        "SimulationMessage* simulationMessagePtr1 = unknown;",
        "IAsyncResult asyncResult1 = task;",
        "List<int> list1 = new List<int>();",
        "T value1 = default;",
        "RTHandle rtHandle1 = handle;",
        "TMP_CharacterInfo[] tmpCharacterInfoArray1 = info;",
    ]


def test_semantic_names_avoid_even_unused_parameter_collisions():
    dec = decompiler()
    dec.L = SimpleNamespace(
        meta=SimpleNamespace(
            method_params=lambda method: [SimpleNamespace(name="gameObject1")]
        )
    )

    assert dec._semantic_local_names(
        ["GameObject obj1 = new GameObject();"], method=object()
    ) == ["GameObject gameObject2 = new GameObject();"]


def test_conflicting_or_untracked_declarations_keep_honest_obj_name():
    lines = [
        "object obj1 = unknown;",
        "GameObject obj1 = other;",
        "obj1.SetActive(true);",
        "object obj2 = unknown;",
    ]

    assert decompiler()._semantic_local_names(lines) == lines


def test_explicit_reference_rhs_refines_single_definition_object_locals():
    lines = [
        'object obj1 = new string[8];',
        'obj1[0] = "x";',
        'object obj2 = typeof(GameObject);',
        'if (obj2 != null)',
        '{',
        '    object obj3 = "obj1 stays literal";',
        '    Consume(obj3);',
        '}',
        'object obj4 = new int[num1, num2][];',
        'Consume(obj4);',
    ]

    assert decompiler()._semantic_local_names(lines) == [
        'string[] textArray1 = new string[8];',
        'textArray1[0] = "x";',
        'System.Type type1 = typeof(GameObject);',
        'if (type1 != null)',
        '{',
        '    string text1 = "obj1 stays literal";',
        '    Consume(text1);',
        '}',
        'int[,][] intArray1 = new int[num1, num2][];',
        'Consume(intArray1);',
    ]


def test_explicit_rhs_refinement_refuses_reassignment_and_byref_escape():
    lines = [
        'object obj1 = new string[8];',
        'obj1 = other;',
        'object obj2 = typeof(GameObject);',
        'Consume(ref obj2);',
        'object obj3 = "text";',
        'Consume(&obj3);',
    ]

    assert decompiler()._semantic_local_names(lines) == lines


def test_array_rank_counts_only_top_level_dimension_commas():
    assert Decompiler._semantic_explicit_rhs_type(
        "new int[Math.Max(left, right)]"
    ) == "int[]"
    assert Decompiler._semantic_explicit_rhs_type(
        "new int[width, height]"
    ) == "int[,]"
    assert Decompiler._semantic_explicit_rhs_type(
        "new int[Compare<T, U>()]"
    ) is None


def test_return_equality_is_not_misread_as_a_second_declaration():
    lines = [
        "char obj1 = value;",
        "return obj1 == 36;",
    ]
    assert decompiler()._semantic_local_names(lines) == [
        "char character1 = value;",
        "return character1 == 36;",
    ]
