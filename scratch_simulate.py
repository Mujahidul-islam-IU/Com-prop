import re

def better_parse_price(raw_price):
    if not raw_price:
        return ""
        
    pattern = r'(?i)(?:\$\s*[\d,\.]+\s*(?:million|millions|mil|m)?\b)|(?:[\d,\.]+\s*(?:million|millions|mil|m)\b)|(?:\b\d{1,3}(?:,\d{3})+\b)'
    matches = re.findall(pattern, raw_price)
    
    if not matches:
        return ""
        
    parsed_prices = []
    
    for match in matches:
        match = match.strip()
        is_millions = bool(re.search(r'(?i)million|millions|mil|m\b', match))
        
        clean_num = re.sub(r'[^\d\.]', '', match)
        
        if clean_num.count('.') > 1:
            clean_num = clean_num.rstrip('.')
            if clean_num.count('.') > 1:
                parts = clean_num.split('.')
                clean_num = parts[0] + '.' + ''.join(parts[1:])
                
        if not clean_num:
            continue
            
        try:
            val = float(clean_num)
            if is_millions and val < 1000:
                val = val * 1_000_000
                
            if val > 10:
                formatted = f"${int(val):,}" if val % 1 == 0 else f"${val:,.2f}"
                if formatted not in parsed_prices:
                    parsed_prices.append(formatted)
        except ValueError:
            pass
            
    if parsed_prices:
        if len(parsed_prices) == 1:
            return parsed_prices[0]
        else:
            return " - ".join(parsed_prices)
            
    return ""

tests = [
    "From $751,200 to $840,000 + GST",
    "$2,950,000 - $3,300,000 plus GST (under offer)",
    "For Sale, Offers over $1.35 million",
    "For Sale, Offers over $2.695 Million",
    "$2.5M",
    "$29,500,003.30",
    "$1,350,000",
    "$825,000",
    "Contact Agent",
    "210 m2",
    "26 30 31 32 59 60 something $575,000",
    "Offers over 1.5 million"
]

for t in tests:
    print(f"{t:50} -> {better_parse_price(t)}")
