import os
import glob

templates_dir = r'c:\Users\ASUS\Desktop\TravelMate\project\templates'
vendor_dir = r'c:\Users\ASUS\Desktop\TravelMate\project\vendor\templates\vendor'

files = []
for d in [templates_dir, vendor_dir]:
    for root, dirs, filenames in os.walk(d):
        for f in filenames:
            if f.endswith('.html'):
                files.append(os.path.join(root, f))

count = 0
for filepath in files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content.replace('${{', 'Rs {{')
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        count += 1
        print(f'Updated: {os.path.basename(filepath)}')

print(f'\nTotal files updated: {count}')
