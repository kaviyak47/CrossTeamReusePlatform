def compute_take_home_pay(monthly_salary: float, extra_hours: float, rate_per_hour: float, tax_rate: float) -> dict:
    """Compute worker monthly take-home earnings with extra time and mandatory deductions."""
    extra_pay = extra_hours * rate_per_hour * 1.5
    total_gross = monthly_salary + extra_pay
    deducted_tax = total_gross * tax_rate
    pension_deduction = total_gross * 0.05
    final_net_income = total_gross - (deducted_tax + pension_deduction)
    
    return {
        "gross": round(total_gross, 2),
        "tax": round(deducted_tax, 2),
        "retirement": round(pension_deduction, 2),
        "net": round(final_net_income, 2),
    }
