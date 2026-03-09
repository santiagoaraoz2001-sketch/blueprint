import os
import sys
try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image, ImageDraw, ImageFilter

def create_mac_icon(input_path, output_path):
    size = 1024
    icon_size = 824
    radius = int(icon_size * 0.225)

    out = Image.new('RGBA', (size, size), (0,0,0,0))

    try:
        img = Image.open(input_path).convert('RGBA')
    except Exception as e:
        print(f"Error opening image: {e}")
        return

    img = img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)

    # Create mask for rounded rectangle
    mask = Image.new('L', (icon_size, icon_size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, icon_size, icon_size), radius, fill=255)

    # Add drop shadow
    shadow = Image.new('RGBA', (size, size), (0,0,0,0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_offset_y = 24
    shadow_draw.rounded_rectangle(
        ((size - icon_size)//2, (size - icon_size)//2 + shadow_offset_y, 
         (size + icon_size)//2, (size + icon_size)//2 + shadow_offset_y), 
        radius, fill=(0,0,0,100)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(20))
    
    # Also add a slight inner/bottom rim shadow to the main base maybe?
    # Simple shadow is enough

    offset_x = (size - icon_size) // 2
    offset_y = (size - icon_size) // 2

    final_img = Image.new('RGBA', (icon_size, icon_size), (0,0,0,0))
    final_img.paste(img, (0,0), mask)

    # Composite
    out.paste(shadow, (0,0), shadow)
    out.paste(final_img, (offset_x, offset_y), final_img)

    out.save(output_path)
    print(f"Saved squircle to {output_path}")

create_mac_icon("Blueprint Icon.jpg", "icon_512x512@2x.png")
