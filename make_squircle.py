import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import math

def create_superellipse_mask(size, n=5.0):
    mask = Image.new('L', (size, size), 0)
    pixels = mask.load()
    center_x = size / 2.0
    center_y = size / 2.0
    a = size / 2.0
    
    # Calculate superellipse
    for y in range(size):
        for x in range(size):
            dx = abs(x + 0.5 - center_x) / a
            dy = abs(y + 0.5 - center_y) / a
            if (dx**n + dy**n) <= 1.0:
                pixels[x, y] = 255
            else:
                # Anti-aliasing approximation (subpixel sampling)
                hits = 0
                for sx in [-0.25, 0.25]:
                    for sy in [-0.25, 0.25]:
                        spx = abs((x + 0.5 + sx) - center_x) / a
                        spy = abs((y + 0.5 + sy) - center_y) / a
                        if (spx**n + spy**n) <= 1.0:
                            hits += 1
                if hits > 0:
                    pixels[x,y] = int(255 * (hits/4.0))
    return mask

def make_perfect_icon(input_path, output_path):
    size = 1024
    icon_size = 824
    
    out = Image.new('RGBA', (size, size), (0,0,0,0))
    img = Image.open(input_path).convert('RGBA')
    img = img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
    
    mask = create_superellipse_mask(icon_size, n=4.8) # 4.8 closely matches Apple's continuous curve
    
    final_img = Image.new('RGBA', (icon_size, icon_size), (0,0,0,0))
    final_img.paste(img, (0,0), mask)
    
    # Drop shadow
    shadow_offset_y = 20
    shadow = Image.new('RGBA', (size, size), (0,0,0,0))
    shadow.paste(Image.new('RGBA', (icon_size, icon_size), (0,0,0, 160)), 
                 ((size - icon_size)//2, (size - icon_size)//2 + shadow_offset_y), mask)
    
    shadow = shadow.filter(ImageFilter.GaussianBlur(24))
    
    offset_x = (size - icon_size) // 2
    offset_y = (size - icon_size) // 2
    
    out.paste(shadow, (0,0), shadow)
    out.paste(final_img, (offset_x, offset_y), final_img)
    
    out.save(output_path)
    print("Squircle perfect saved!")

make_perfect_icon("Blueprint Icon.jpg", "icon_512x512@2x.png")
