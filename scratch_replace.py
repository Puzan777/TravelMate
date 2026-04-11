import os
import glob

directory = r'c:\Users\ASUS\Desktop\TravelMate\project\vendor\templates\vendor'
files = glob.glob(os.path.join(directory, '*_list.html'))
files.append(os.path.join(directory, 'package_availability.html'))
files.append(os.path.join(directory, 'activity_availability.html'))

target1 = '<button type="submit" class="vd-btn-primary" style="justify-content: center;">Apply</button>'
new1 = '<button type="submit" class="vd-btn-primary" style="justify-content: center;">Search</button>'

target2 = '<button type="submit" class="vd-btn-primary">Apply</button>'
new2 = '<button type="submit" class="vd-btn-primary">Search</button>'

for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
        
        if target1 in content or target2 in content:
            new_content = content.replace(target1, new1).replace(target2, new2)
            with open(f, 'w', encoding='utf-8') as file:
                file.write(new_content)
            print(f'Updated {os.path.basename(f)}')
    except Exception as e:
        pass
