def calculate_net_salary(base_pay: float, overtime_hours: float, hourly_rate: float, tax_bracket: float) -> dict:
    """Calculate total net compensation for an employee including overtime and taxes."""
    overtime_compensation = overtime_hours * (hourly_rate * 1.5)
    gross_earnings = base_pay + overtime_compensation
    tax_withholding = gross_earnings * tax_bracket
    retirement_contribution = gross_earnings * 0.05
    take_home_pay = gross_earnings - tax_withholding - retirement_contribution
    
    return {
        "gross": round(gross_earnings, 2),
        "tax": round(tax_withholding, 2),
        "retirement": round(retirement_contribution, 2),
        "net": round(take_home_pay, 2),
    }
