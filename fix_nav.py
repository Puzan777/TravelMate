import sys

filepath = r'c:\Users\ASUS\Desktop\TravelMate\project\templates\admin\base_site.html'
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. We must extract the entire <nav id="nav-sidebar">...</nav>
nav_start = text.find('<nav class="sticky tm-curated-nav" id="nav-sidebar"')
if nav_start == -1:
    print("Could not find nav-sidebar")
    sys.exit(1)

nav_end = text.find('</nav>', nav_start) + 6
nav_html = text[nav_start:nav_end]

# 2. We remove this block entirely from where it currently sits
text = text[:nav_start] + text[nav_end:]

# 3. We look for </header> which closes the header block, and inject nav_html immediately AFTER it!
header_close_idx = text.find('</header>') + 9
if header_close_idx == 8: # None + 9
    print("Could not find header close")
    sys.exit(1)

text = text[:header_close_idx] + '\n\n<!-- FOOLPROOF SIDEBAR INJECTION -->\n' + nav_html + '\n\n' + text[header_close_idx:]

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(text)
print("SUCCESS")
