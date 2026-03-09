#!/usr/bin/env python3
"""
Generate Blueprint macOS app icon — 1024x1024 PNG.
Matches the Specific Labs Control Tower style:
  - Black (#0A0A0A) background with macOS squircle mask
  - White line-art illustration (microscope — ML research tool) in center
  - Specific Labs logomark (L-bracket + cyan circle) in top-right corner
"""

from PIL import Image, ImageDraw
import math
import os

SIZE = 1024
WHITE = (255, 255, 255)
BG = (10, 10, 10)           # #0A0A0A
CYAN = (74, 246, 195)       # #4AF6C3

# Line weight: ~3px at display size → ~28px at 1024
LW = int(SIZE * 0.027)


def create_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def draw_microscope(img: Image.Image, cx: int, cy: int, s: float):
    """
    Draw a clean geometric microscope using line-art strokes.
    s = overall scale factor.
    """
    draw = ImageDraw.Draw(img)

    # Key coordinates
    base_y = int(cy + 195 * s)
    pillar_x = int(cx + 50 * s)

    # ── 1. BASE — wide horizontal platform ──
    draw.rounded_rectangle(
        [int(cx - 155 * s), base_y,
         int(cx + 155 * s), base_y + int(20 * s)],
        radius=int(6 * s),
        outline=WHITE, width=LW,
    )

    # Feet / risers under base
    foot_w = int(14 * s)
    foot_h = int(10 * s)
    for fx in [int(cx - 110 * s), int(cx + 110 * s)]:
        draw.rectangle(
            [fx - foot_w // 2, base_y + int(20 * s),
             fx + foot_w // 2, base_y + int(20 * s) + foot_h],
            fill=WHITE,
        )

    # ── 2. STAGE — horizontal sample platform ──
    stage_y = int(cy + 55 * s)
    stage_left = int(cx - 100 * s)
    stage_right = int(cx + 100 * s)
    draw.rounded_rectangle(
        [stage_left, stage_y, stage_right, stage_y + int(14 * s)],
        radius=int(4 * s),
        outline=WHITE, width=LW,
    )

    # Stage clips (small vertical ticks)
    for clip_x in [int(cx - 55 * s), int(cx + 55 * s)]:
        draw.rectangle(
            [clip_x - int(3 * s), stage_y - int(10 * s),
             clip_x + int(3 * s), stage_y],
            fill=WHITE,
        )

    # ── 3. PILLAR — vertical column (right side) from base to top ──
    pillar_top = int(cy - 195 * s)

    draw.rectangle(
        [pillar_x - LW, pillar_top, pillar_x + LW, base_y],
        fill=WHITE,
    )

    # ── 4. ARM — horizontal from pillar toward the left ──
    arm_y = pillar_top
    arm_left = int(cx - 50 * s)

    draw.rectangle(
        [arm_left, arm_y, pillar_x + LW, arm_y + LW + int(4 * s)],
        fill=WHITE,
    )

    # ── 5. BODY TUBE — from arm downward toward stage (slightly angled) ──
    tube_top_x = arm_left + int(5 * s)
    tube_top_y = arm_y + LW + int(4 * s)
    tube_bot_x = int(cx - 20 * s)
    tube_bot_y = stage_y - int(14 * s)

    # Draw tube as thick line
    draw.line(
        [(tube_top_x, tube_top_y), (tube_bot_x, tube_bot_y)],
        fill=WHITE, width=int(LW * 2.0),
    )

    # ── 6. EYEPIECE — barrel at top of body tube ──
    ep_cx = tube_top_x - int(18 * s)
    ep_cy = arm_y - int(8 * s)
    ep_w = int(18 * s)
    ep_h = int(40 * s)

    # Connecting neck from tube to eyepiece
    draw.line(
        [(ep_cx, ep_cy + ep_h // 3), (tube_top_x, tube_top_y - int(5 * s))],
        fill=WHITE, width=int(LW * 1.5),
    )

    # Eyepiece barrel (outline)
    draw.rounded_rectangle(
        [ep_cx - ep_w, ep_cy - ep_h // 2,
         ep_cx + ep_w, ep_cy + ep_h // 3],
        radius=int(5 * s),
        outline=WHITE, width=LW,
    )

    # Eyepiece rim at top
    draw.line(
        [(ep_cx - ep_w - int(4 * s), ep_cy - ep_h // 2),
         (ep_cx + ep_w + int(4 * s), ep_cy - ep_h // 2)],
        fill=WHITE, width=LW,
    )

    # ── 7. OBJECTIVE LENS — at bottom of tube near stage ──
    obj_cx = tube_bot_x
    obj_cy = tube_bot_y + int(5 * s)
    obj_w = int(20 * s)
    obj_h = int(18 * s)

    draw.rounded_rectangle(
        [obj_cx - obj_w, obj_cy,
         obj_cx + obj_w, obj_cy + obj_h],
        radius=int(4 * s),
        outline=WHITE, width=LW,
    )

    # Nosepiece (turret above objective — small circle)
    np_cx = int((tube_top_x + tube_bot_x) // 2)
    np_cy = int((tube_top_y + tube_bot_y) // 2) - int(10 * s)
    np_r = int(12 * s)
    draw.ellipse(
        [np_cx - np_r, np_cy - np_r, np_cx + np_r, np_cy + np_r],
        outline=WHITE, width=max(LW // 2, 2),
    )

    # ── 8. FOCUS KNOBS — circles on the pillar ──
    for ky_offset in [int(30 * s), int(-40 * s)]:
        knob_cx = pillar_x + int(24 * s)
        knob_cy = int(cy + ky_offset)
        knob_r = int(16 * s)

        draw.ellipse(
            [knob_cx - knob_r, knob_cy - knob_r,
             knob_cx + knob_r, knob_cy + knob_r],
            outline=WHITE, width=LW,
        )
        # Inner dot
        ir = int(4 * s)
        draw.ellipse(
            [knob_cx - ir, knob_cy - ir, knob_cx + ir, knob_cy + ir],
            fill=WHITE,
        )

    # ── 9. SUPPORT ARM — angled brace from pillar to base ──
    sup_start_y = int(cy + 120 * s)
    sup_end_x = int(cx - 50 * s)

    draw.line(
        [(pillar_x - LW, sup_start_y), (sup_end_x, base_y)],
        fill=WHITE, width=LW,
    )


def draw_logomark(draw: ImageDraw.Draw, x: int, y: int, size: int):
    """Draw the Specific Labs logomark (L-bracket + cyan circle)."""
    s = size / 120.0
    bracket_w = int(120 * s)
    bar_thick = int(24 * s)
    circle_r = int(36 * s)
    circle_cx = x + int(36 * s)
    circle_cy = y + int(84 * s)

    # L-bracket polygon
    points = [
        (x, y),
        (x + bracket_w, y),
        (x + bracket_w, y + bracket_w),
        (x + bracket_w - bar_thick, y + bracket_w),
        (x + bracket_w - bar_thick, y + bar_thick),
        (x, y + bar_thick),
    ]
    draw.polygon(points, fill=WHITE)

    # Cyan circle
    draw.ellipse(
        [circle_cx - circle_r, circle_cy - circle_r,
         circle_cx + circle_r, circle_cy + circle_r],
        fill=CYAN,
    )


def create_icon():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    corner_radius = int(SIZE * 0.22)
    mask = create_mask(SIZE, corner_radius)

    # ── Background ──
    draw.rounded_rectangle(
        [0, 0, SIZE - 1, SIZE - 1],
        radius=corner_radius,
        fill=BG,
    )

    # ── Subtle inner border ──
    draw.rounded_rectangle(
        [3, 3, SIZE - 4, SIZE - 4],
        radius=corner_radius - 2,
        outline=(255, 255, 255, 15),
        width=1,
    )

    # ── Microscope — centered ──
    draw_microscope(img, cx=SIZE // 2 - 15, cy=SIZE // 2 + 20, s=0.95)

    # ── Specific Labs logomark (top-right corner) ──
    logo_size = int(SIZE * 0.12)
    logo_margin = int(SIZE * 0.075)
    draw_logomark(draw, x=SIZE - logo_margin - logo_size, y=logo_margin, size=logo_size)

    # ── Apply mask ──
    final = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    final.paste(img, (0, 0), mask)

    # ── Save ──
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "icon.png")
    final.save(out_path, "PNG")
    print(f"Icon saved to {out_path} ({SIZE}x{SIZE})")

    # Generate iconset for macOS .icns
    iconset_dir = os.path.join(out_dir, "icon.iconset")
    os.makedirs(iconset_dir, exist_ok=True)

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for sz in sizes:
        resized = final.resize((sz, sz), Image.LANCZOS)
        resized.save(os.path.join(iconset_dir, f"icon_{sz}x{sz}.png"))
        if sz <= 512:
            resized_2x = final.resize((sz * 2, sz * 2), Image.LANCZOS)
            resized_2x.save(os.path.join(iconset_dir, f"icon_{sz}x{sz}@2x.png"))

    print(f"Iconset saved to {iconset_dir}")
    print("Run: iconutil -c icns icon.iconset")


if __name__ == "__main__":
    create_icon()
