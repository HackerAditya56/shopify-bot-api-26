"""
LEGEND CHECKER - CC Generator Functions
Owner: @LEGEND_BL

Functions for generating credit card numbers.
"""

import random
from TOOLS.cc_utils import calculate_luhn_digit


def generate_cc(bin_number, count=10):
    """
    Generate random credit card numbers based on BIN
    
    Args:
        bin_number: The BIN (first 6 digits)
        count: Number of cards to generate
    
    Returns:
        List of generated CC in format cc|mm|yy|cvv
    """
    generated = []
    bin_str = str(bin_number)[:6]
    
    # Pad BIN to 6 digits if needed
    while len(bin_str) < 6:
        bin_str += 'x'
    
    for _ in range(count):
        # Generate card number
        card = ""
        for char in bin_str:
            if char == 'x' or not char.isdigit():
                card += str(random.randint(0, 9))
            else:
                card += char
        
        # Complete to 15 digits (16 - 1 for checksum)
        while len(card) < 15:
            card += str(random.randint(0, 9))
        
        # Calculate and append Luhn checksum digit efficiently
        check_digit = calculate_luhn_digit(card)
        card = card + str(check_digit)
        
        # Generate expiry date
        month = str(random.randint(1, 12)).zfill(2)
        year = str(random.randint(25, 30))  # 2025-2030
        
        # Generate CVV
        cvv = str(random.randint(100, 999))
        
        # Format CC
        cc_data = f"{card}|{month}|{year}|{cvv}"
        
        if cc_data not in generated:
            generated.append(cc_data)
    
    return generated


def format_generated_cc(cc_list):
    """Format list of generated CC for display"""
    return "\n".join(cc_list)


async def luhn_card_genarator(bin_input, month=None, year=None, cvv=None, amount=10):
    """
    Generate credit cards with Luhn algorithm validation
    
    Args:
        bin_input: BIN number (can include x for random)
        month: Expiry month (optional)
        year: Expiry year (optional)
        cvv: CVV (optional)
        amount: Number of cards to generate
        
    Returns:
        String of generated cards separated by newlines
    """
    generated = []
    bin_str = str(bin_input)
    
    # Pad with x if less than 16
    while len(bin_str) < 16:
        bin_str += 'x'
    
    # Limit BIN to 16 characters
    bin_str = bin_str[:16]
    
    for _ in range(amount):
        # Generate card number
        card = ""
        for i, char in enumerate(bin_str):
            if i == 15:  # Last digit will be Luhn check digit
                break
            if char == 'x' or not char.isdigit():
                card += str(random.randint(0, 9))
            else:
                card += char
        
        # Calculate and append Luhn checksum digit
        check_digit = calculate_luhn_digit(card)
        card = card + str(check_digit)
        
        # Generate expiry date
        if month:
            exp_month = str(month).zfill(2)
        else:
            exp_month = str(random.randint(1, 12)).zfill(2)
        
        if year:
            exp_year = str(year).zfill(2) if len(str(year)) <= 2 else str(year)[-2:]
        else:
            exp_year = str(random.randint(25, 30))
        
        # Generate CVV
        if cvv:
            card_cvv = str(cvv).zfill(3)
        else:
            card_cvv = str(random.randint(100, 999))
        
        # Format CC
        cc_data = f"{card}|{exp_month}|{exp_year}|{card_cvv}"
        
        if cc_data not in generated:
            generated.append(cc_data)
    
    return "\n".join(generated)
