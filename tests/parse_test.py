import re
from bs4 import BeautifulSoup

html = open('page.html', encoding='utf-8').read()
soup = BeautifulSoup(html, 'html.parser')

# Title
h2s = soup.find_all('h2')
title = ''
for h2 in h2s:
    if len(h2.text) > 10 and 'Property Description' not in h2.text and 'Highlights' not in h2.text:
        title = h2.text.strip()
        break
print('Title:', title)

# Price
price = ''
for el in soup.find_all(string=re.compile(r'Please contact agent|Asking Price|\$|For Lease, Please contact agent')):
    p = el.parent
    if p and len(p.text) < 50 and ('$' in p.text or 'contact' in p.text.lower() or 'price' in p.text.lower()):
        price = p.text.strip()
        break
print('Price:', price)

# Size
size = ''
area_node = soup.find(string=re.compile('Floor Area|Building Area|Land Area'))
if area_node and area_node.parent:
    parent = area_node.parent
    sibling = parent.find_next_sibling()
    if sibling:
        size = sibling.text.strip()
    else:
        full_text = parent.parent.text
        size = full_text.replace(area_node.strip(), '').strip()
print('Size:', size)

# PropertyType
ptype = ''
crumbs = soup.select('nav[aria-label="Breadcrumb"] a')
if len(crumbs) >= 3:
    ptype = crumbs[2].text.strip()
print('PType:', ptype)
