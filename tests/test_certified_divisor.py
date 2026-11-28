from il2cpp.boxed_quotient import certified_divisor


def test_multiplier_needs_strict_positive_error_below_a_quotient_interval():
    assert certified_divisor(0x88888889, 5) == 60
    assert certified_divisor(0xaaaaaaab, 1) == 3
    assert certified_divisor(0x88888899, 5) is None
    assert certified_divisor(0x80000000, 0) is None  # exact negative multiples overcorrect
    assert certified_divisor(0x66666667, 3) is None  # no signed-high ADD correction
