import re

def parse_price(raw_price):
    if not raw_price:
        return ""
    is_millions = bool(re.search(r'\b(million|millions|mil)\b', raw_price, re.IGNORECASE)) or \
                  bool(re.search(r'\$[\d,\.]+\s*[Mm]\b(?!²|2|illion)', raw_price))
    cleaned = re.sub(r"[^\d\.]", "", raw_price)
    if cleaned:
        try:
            # Handle edge cases with multiple dots like "1.35."
            if cleaned.count('.') > 1:
                # keep up to the first dot, or remove the last dot? 
                # e.g., "1.35." -> "1.35"
                cleaned = cleaned.rstrip('.')
                if cleaned.count('.') > 1: # if still multiple dots, remove all but first
                    parts = cleaned.split('.')
                    cleaned = parts[0] + '.' + ''.join(parts[1:])
            price_num = float(cleaned)
            if is_millions:
                price_num = price_num * 1_000_000
            return f"${int(price_num):,}" if price_num % 1 == 0 else f"${price_num:,.2f}"
        except ValueError:
            return ""
    return ""

tests = [
    ("For Sale, Offers over $1.35 million",   "$1,350,000"),
    ("For Sale, Offers over $2.695 Million",  "$2,695,000"),
    ("$2.5M",                                 "$2,500,000"),
    ("$29,500,003.30",                        "$29,500,003.30"),
    ("$1,350,000",                            "$1,350,000"),
    ("$825,000",                              "$825,000"),
    ("Contact Agent",                          ""),
    ("210 m2",                                 ""),
]

all_pass = True
for raw, expected in tests:
    result = parse_price(raw)
    status = "PASS" if result == expected else "FAIL"
    if status == "FAIL":
        all_pass = False
    print(f"[{status}]  {raw!r:45} -> {result!r}  (expected {expected!r})")

print()
print("All tests passed!" if all_pass else "SOME TESTS FAILED!")
