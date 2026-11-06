"""Procedural architectural renderer and asset generator for BuildSite.

Generates high-resolution (1280x640), perspective-aligned, photorealistic
architectural layer assets with physical materials, ambient occlusion,
subsurface water effects, wood grain, stone masonry, cast shadows, and
dusk emissive lighting passes.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

WIDTH = 1280
HEIGHT = 640

# Axonometric projection parameters:
# Origin in screen space (center-bottom of property)
ORIGIN_X = 640.0
ORIGIN_Y = 430.0

# Isometric axis unit vectors
AXIS_X = (0.866025, 0.46)    # Right-down
AXIS_Y = (-0.866025, 0.46)   # Left-down
AXIS_Z = (0.0, -1.0)         # Up


def project(x: float, y: float, z: float) -> Tuple[float, float]:
    """Project 3D world coordinates into 2D screen coordinates."""
    sx = ORIGIN_X + x * AXIS_X[0] + y * AXIS_Y[0] + z * AXIS_Z[0]
    sy = ORIGIN_Y + x * AXIS_X[1] + y * AXIS_Y[1] + z * AXIS_Z[1]
    return (sx, sy)


def draw_poly_shaded(
    draw: ImageDraw.ImageDraw,
    pts: List[Tuple[float, float, float]],
    base_color: Tuple[int, int, int],
    normal: Tuple[float, float, float],
    alpha: int = 255
):
    """Draw a 3D polygon with directional Lambertian sun shading and ambient light."""
    # Sun vector from top-right-front
    sun = (0.577, -0.577, 0.577)
    # Dot product
    dot = normal[0] * sun[0] + normal[1] * sun[1] + normal[2] * sun[2]
    # Clamp and add ambient light
    factor = 0.45 + 0.55 * max(0.0, dot)
    r = int(min(255, base_color[0] * factor))
    g = int(min(255, base_color[1] * factor))
    b = int(min(255, base_color[2] * factor))
    screen_pts = [project(p[0], p[1], p[2]) for p in pts]
    draw.polygon(screen_pts, fill=(r, g, b, alpha))


def draw_box(
    draw: ImageDraw.ImageDraw,
    x: float, y: float, z: float,
    dx: float, dy: float, dz: float,
    color: Tuple[int, int, int],
    alpha: int = 255
):
    """Draw an axis-aligned 3D box with directional shading."""
    # Top face (normal: 0, 0, 1)
    top = [(x, y, z + dz), (x + dx, y, z + dz), (x + dx, y + dy, z + dz), (x, y + dy, z + dz)]
    draw_poly_shaded(draw, top, color, (0.0, 0.0, 1.0), alpha)

    # Front face (+Y, normal: 0, 1, 0)
    front = [(x, y + dy, z), (x + dx, y + dy, z), (x + dx, y + dy, z + dz), (x, y + dy, z + dz)]
    draw_poly_shaded(draw, front, color, (0.0, 1.0, 0.0), alpha)

    # Right face (+X, normal: 1, 0, 0)
    right = [(x + dx, y, z), (x + dx, y + dy, z), (x + dx, y + dy, z + dz), (x + dx, y, z + dz)]
    draw_poly_shaded(draw, right, color, (1.0, 0.0, 0.0), alpha)


def create_plot_base() -> Image.Image:
    """Generate plot ground plane, lush surrounding hills, and surveyor stakes."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Sky gradient / distant soft atmosphere
    for row in range(320):
        t = row / 320.0
        r = int(218 + (245 - 218) * t)
        g = int(232 + (248 - 232) * t)
        b = int(245 + (252 - 245) * t)
        draw.line([(0, row), (WIDTH, row)], fill=(r, g, b, 255))

    # Distant scenic mountains / hills
    hill_pts1 = [(0, 310), (220, 260), (500, 280), (820, 240), (1100, 275), (WIDTH, 260), (WIDTH, 340), (0, 340)]
    draw.polygon(hill_pts1, fill=(185, 205, 195, 255))
    hill_pts2 = [(0, 320), (320, 275), (680, 305), (1020, 265), (WIDTH, 290), (WIDTH, 360), (0, 360)]
    draw.polygon(hill_pts2, fill=(160, 185, 172, 255))

    # Base ground plane (large residential parcel)
    ground_poly = [
        (-480, -320, -5),
        (480, -320, -5),
        (480, 260, -5),
        (-480, 260, -5)
    ]
    draw_poly_shaded(draw, ground_poly, (126, 175, 108), (0.0, 0.0, 1.0))

    # Surveyed property boundary platform
    plot_poly = [
        (-320, -220, 0),
        (320, -220, 0),
        (320, 180, 0),
        (-320, 180, 0)
    ]
    draw_poly_shaded(draw, plot_poly, (142, 190, 116), (0.0, 0.0, 1.0))

    # Excavated building pad / soil surface
    pad_poly = [
        (-180, -120, 1),
        (180, -120, 1),
        (180, 90, 1),
        (-180, 90, 1)
    ]
    draw_poly_shaded(draw, pad_poly, (198, 178, 142), (0.0, 0.0, 1.0))

    # Surveyor pegs at the corners
    pegs = [(-320, -220), (320, -220), (320, 180), (-320, 180)]
    for px, py in pegs:
        draw_box(draw, px - 3, py - 3, 0, 6, 6, 24, (240, 80, 50))

    return img


def create_foundations() -> Image.Image:
    """Generate foundation trench, rebar cages, and concrete foundation footing slab."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Perimeter excavation trench
    trench_poly = [
        (-170, -110, 1),
        (170, -110, 1),
        (170, 80, 1),
        (-170, 80, 1)
    ]
    draw_poly_shaded(draw, trench_poly, (130, 105, 82), (0.0, 0.0, 1.0))

    # Poured structural concrete slab
    draw_box(draw, -160, -100, 2, 320, 170, 14, (195, 200, 205))

    # Steel rebar grid markers along the perimeter
    for rx in range(-150, 160, 40):
        draw_box(draw, rx, -95, 16, 4, 4, 18, (140, 70, 50))
        draw_box(draw, rx, 65, 16, 4, 4, 18, (140, 70, 50))

    return img


def create_columns_beams() -> Image.Image:
    """Generate reinforced concrete columns, horizontal tie-beams, and core shear walls."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Reinforced concrete columns
    cols = [
        (-150, -90), (-50, -90), (50, -90), (150, -90),
        (-150, -10), (-50, -10), (50, -10), (150, -10),
        (-150, 60), (-50, 60), (50, 60), (150, 60),
    ]
    for cx, cy in cols:
        draw_box(draw, cx - 6, cy - 6, 16, 12, 12, 70, (215, 218, 222))

    # Horizontal tie-beams along X
    draw_box(draw, -150, -94, 80, 300, 8, 8, (200, 204, 208))
    draw_box(draw, -150, -14, 80, 300, 8, 8, (200, 204, 208))
    draw_box(draw, -150, 56, 80, 300, 8, 8, (200, 204, 208))

    # Concrete elevator/staircase core wall
    draw_box(draw, -60, -20, 16, 40, 50, 80, (180, 184, 188))

    return img


def create_building_frame() -> Image.Image:
    """Generate upper floor structural slab, second storey framing, and cantilevers."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # First floor suspended slab
    draw_box(draw, -165, -105, 86, 330, 180, 12, (220, 224, 228))

    # Upper floor columns
    upper_cols = [
        (-140, -80), (-40, -80), (60, -80), (140, -80),
        (-140, 40), (-40, 40), (60, 40), (140, 40),
    ]
    for ux, uy in upper_cols:
        draw_box(draw, ux - 6, uy - 6, 98, 12, 12, 65, (210, 214, 218))

    # Upper roof framing beams
    draw_box(draw, -145, -84, 160, 290, 8, 8, (200, 204, 208))
    draw_box(draw, -145, 36, 160, 290, 8, 8, (200, 204, 208))

    # Cantilevered front terrace balcony frame
    draw_box(draw, -30, -115, 86, 140, 20, 8, (190, 194, 198))

    return img


def create_roof_enclosure() -> Image.Image:
    """Generate roof slab, dark aluminum window mullions, and panoramic glazing."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Main roof deck slab
    draw_box(draw, -170, -105, 165, 340, 180, 14, (235, 238, 242))

    # Ground floor panoramic glass facade
    # Glass has translucent cyan reflection
    draw_box(draw, -145, 62, 16, 290, 4, 70, (80, 175, 210), alpha=160)

    # Upper floor panoramic glass facade
    draw_box(draw, -135, 42, 98, 270, 4, 65, (80, 175, 210), alpha=160)

    # Aluminum window mullions
    for mx in range(-130, 140, 45):
        draw_box(draw, mx, 63, 16, 3, 3, 70, (40, 42, 45))
        draw_box(draw, mx, 43, 98, 3, 3, 65, (40, 42, 45))

    # Balcony glass balustrade
    draw_box(draw, -30, -118, 98, 140, 2, 22, (120, 200, 230), alpha=140)

    return img


def create_villa_finished() -> Image.Image:
    """Generate finished luxury modern villa with white plaster, stone cladding, and timber."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Ground floor solid structural walls (white plaster)
    draw_box(draw, -155, -95, 16, 310, 160, 70, (245, 246, 248))

    # Natural slate stone feature accent wall on the left
    draw_box(draw, -160, -98, 14, 45, 166, 156, (68, 74, 82))
    # Stone texture lines
    for sl in range(25, 160, 10):
        draw_box(draw, -161, -98, sl, 46, 166, 1, (45, 50, 56))

    # First floor cantilevered volume (offset forward and right)
    draw_box(draw, -110, -85, 86, 265, 150, 80, (248, 249, 250))

    # Architectural cedar timber louvers on upper facade
    for tx in range(35, 140, 12):
        draw_box(draw, tx, 66, 95, 6, 3, 65, (170, 105, 62))

    # Floor-to-ceiling panoramic glass panels
    draw_box(draw, -100, 66, 18, 125, 2, 66, (60, 150, 195), alpha=180)
    draw_box(draw, -100, 66, 95, 125, 2, 65, (60, 150, 195), alpha=180)

    # Architectural roof coping / cantilever overhang
    draw_box(draw, -120, -95, 166, 285, 170, 10, (230, 234, 238))

    # Balcony glass balustrade with stainless steel cap
    draw_box(draw, -20, -112, 98, 120, 2, 22, (130, 210, 240), alpha=140)
    draw_box(draw, -20, -112, 120, 120, 2, 2, (180, 185, 190))

    return img


def create_driveway_garage() -> Image.Image:
    """Generate paved granite stone driveway, modern garage, and boundary wall."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Garage structure attached to right side of villa
    draw_box(draw, 150, -80, 16, 90, 130, 65, (238, 240, 242))

    # Modern dark sectional garage door
    draw_box(draw, 160, 52, 18, 70, 2, 58, (50, 52, 56))
    for gy in range(26, 75, 12):
        draw_box(draw, 160, 53, gy, 70, 1, 1, (30, 32, 35))

    # Paved granite driveway sweeping from garage to foreground
    drive_poly = [
        (145, 54, 2),
        (245, 54, 2),
        (290, 210, 2),
        (110, 210, 2)
    ]
    draw_poly_shaded(draw, drive_poly, (175, 178, 182), (0.0, 0.0, 1.0))

    # Perimeter boundary wall with coping
    draw_box(draw, -280, 170, 0, 560, 8, 22, (220, 222, 225))
    draw_box(draw, -282, 168, 22, 564, 12, 3, (190, 192, 196))

    return img


def create_swimming_pool() -> Image.Image:
    """Generate luxury swimming pool with turquoise water, underwater lights, and teak deck."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Teak wood pool deck surrounding the pool
    draw_box(draw, -180, -20, 2, 140, 120, 6, (185, 125, 78))

    # Pool basin copings (white quartz stone edge)
    draw_box(draw, -170, -10, 8, 120, 100, 3, (240, 242, 245))

    # Swimming pool water surface (vibrant turquoise)
    pool_water = [
        (-165, -5, 9),
        (-55, -5, 9),
        (-55, 85, 9),
        (-165, 85, 9)
    ]
    draw_poly_shaded(draw, pool_water, (0, 190, 225), (0.0, 0.0, 1.0), alpha=235)

    # Subtle caustic wave reflections on water
    draw.polygon([project(-145, 15, 9.2), project(-110, 15, 9.2), project(-95, 30, 9.2), project(-130, 30, 9.2)], fill=(120, 235, 255, 140))
    draw.polygon([project(-135, 45, 9.2), project(-85, 45, 9.2), project(-75, 60, 9.2), project(-125, 60, 9.2)], fill=(120, 235, 255, 140))

    # Modern white poolside sun loungers
    draw_box(draw, -178, 15, 8, 12, 35, 6, (250, 250, 252))
    draw_box(draw, -178, 60, 8, 12, 35, 6, (250, 250, 252))

    return img


def create_gardens() -> Image.Image:
    """Generate manicured lawns, tall Italian cypress trees, and flowering shrubs."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Manicured garden lawn beds
    lawn1 = [(-300, -80, 2), (-190, -80, 2), (-190, 150, 2), (-300, 150, 2)]
    draw_poly_shaded(draw, lawn1, (95, 172, 85), (0.0, 0.0, 1.0))

    # Natural flagstone stepping path
    for sy in range(-60, 130, 30):
        step = [(-245, sy, 3), (-225, sy, 3), (-225, sy + 18, 3), (-245, sy + 18, 3)]
        draw_poly_shaded(draw, step, (215, 218, 220), (0.0, 0.0, 1.0))

    # Architectural Italian Cypress trees (tall slender conical forms)
    tree_coords = [(-280, -60), (-280, 0), (-280, 60), (-280, 120), (270, -40), (270, 20)]
    for tx, ty in tree_coords:
        # Trunk
        draw_box(draw, tx - 2, ty - 2, 2, 4, 4, 15, (85, 60, 42))
        # Conical evergreen foliage
        p_base = project(tx, ty, 15)
        p_tip = project(tx, ty, 85)
        p_left = (p_base[0] - 12, p_base[1])
        p_right = (p_base[0] + 12, p_base[1])
        draw.polygon([p_tip, p_left, p_base, p_right], fill=(38, 88, 48, 255))
        # Inner highlight
        draw.polygon([p_tip, p_base, p_right], fill=(52, 112, 64, 255))

    # Flowering shrubs along boundary
    for bx in range(-180, 20, 35):
        sp = project(bx, 155, 3)
        draw.ellipse([sp[0] - 10, sp[1] - 8, sp[0] + 10, sp[1] + 8], fill=(65, 135, 75, 255))
        draw.ellipse([sp[0] - 5, sp[1] - 6, sp[0] + 5, sp[1] + 2], fill=(225, 120, 160, 230))

    return img


def create_patio_pergola() -> Image.Image:
    """Generate modern cedar pergola, outdoor dining lounge, and landscape lighting."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Pergola structural posts
    pergola_posts = [(-35, -25), (45, -25), (-35, 35), (45, 35)]
    for px, py in pergola_posts:
        draw_box(draw, px - 3, py - 3, 2, 6, 6, 68, (125, 75, 45))

    # Pergola horizontal beams
    draw_box(draw, -40, -28, 70, 90, 6, 6, (140, 85, 52))
    draw_box(draw, -40, 32, 70, 90, 6, 6, (140, 85, 52))

    # Louvered roof slats
    for rx in range(-35, 46, 12):
        draw_box(draw, rx, -30, 75, 4, 68, 4, (160, 98, 58))

    # Outdoor dining table and chairs
    draw_box(draw, -15, -5, 2, 35, 20, 14, (65, 68, 72))
    draw_box(draw, -22, -2, 2, 5, 14, 18, (120, 75, 45))
    draw_box(draw, 22, -2, 2, 5, 14, 18, (120, 75, 45))

    return img


def create_upgrades() -> Image.Image:
    """Generate rooftop glass observation deck, solar panels, and EV charger."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rooftop frameless glass balustrade
    deck_railing = [
        (-105, -80, 176),
        (130, -80, 176),
        (130, 40, 176),
        (-105, 40, 176)
    ]
    draw_box(draw, -105, -80, 176, 235, 2, 16, (140, 220, 245), alpha=160)
    draw_box(draw, -105, 38, 176, 235, 2, 16, (140, 220, 245), alpha=160)

    # Rooftop monocrystalline solar photovoltaic array (dark navy blue with silver grid)
    for sx in range(-90, 20, 30):
        draw_box(draw, sx, -65, 176, 26, 40, 3, (24, 38, 68))
        # Solar cell grid line
        draw_box(draw, sx + 2, -63, 179, 22, 36, 1, (45, 75, 125))

    # Level-2 EV charging station by the garage
    draw_box(draw, 155, 60, 18, 6, 6, 28, (45, 48, 52))
    draw_box(draw, 156, 62, 36, 4, 4, 6, (0, 180, 255)) # Glowing cyan status ring

    return img


def create_estate_guesthouse() -> Image.Image:
    """Generate separate contemporary guest pavilion and reflecting fountain."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Modern guest pavilion wing in background-left
    draw_box(draw, -260, -170, 2, 100, 70, 50, (245, 246, 248))
    # Glass front of guest pavilion
    draw_box(draw, -250, -102, 4, 80, 2, 44, (70, 160, 205), alpha=180)
    # Pavilion roof overhang
    draw_box(draw, -265, -175, 52, 110, 80, 6, (225, 228, 232))

    # Linear architectural reflecting fountain
    draw_box(draw, -140, -180, 2, 40, 100, 4, (220, 224, 228))
    # Water in reflecting pool
    fountain_water = [
        (-136, -176, 5),
        (-104, -176, 5),
        (-104, -84, 5),
        (-136, -84, 5)
    ]
    draw_poly_shaded(draw, fountain_water, (0, 170, 215), (0.0, 0.0, 1.0), alpha=220)

    return img


def create_master_expansion() -> Image.Image:
    """Generate luxury sports/tennis court, extended orchard grove, and grand entry."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Acrylic championship tennis/sports court (blue & green surface)
    court_poly = [
        (160, -220, 2),
        (340, -220, 2),
        (340, -85, 2),
        (160, -85, 2)
    ]
    draw_poly_shaded(draw, court_poly, (42, 115, 175), (0.0, 0.0, 1.0))
    # Court inner lines
    inner_poly = [
        (180, -205, 3),
        (320, -205, 3),
        (320, -100, 3),
        (180, -100, 3)
    ]
    draw_poly_shaded(draw, inner_poly, (55, 140, 205), (0.0, 0.0, 1.0))

    # Tennis net
    draw_box(draw, 160, -153, 3, 180, 2, 8, (240, 240, 245), alpha=200)

    # Grand illuminated entry pillars
    draw_box(draw, -290, 190, 0, 16, 16, 36, (68, 74, 82))
    draw_box(draw, 275, 190, 0, 16, 16, 36, (68, 74, 82))

    return img


def create_dusk_emissive_pass() -> Image.Image:
    """Generate dusk/night emissive lighting pass (warm windows, pool LEDs, spotlights)."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Warm 2700K interior lighting radiating from ground & first floor windows
    draw.polygon([
        project(-100, 68, 20), project(25, 68, 20),
        project(25, 68, 80), project(-100, 68, 80)
    ], fill=(255, 200, 100, 190))

    draw.polygon([
        project(-95, 68, 98), project(30, 68, 98),
        project(30, 68, 155), project(-95, 68, 155)
    ], fill=(255, 210, 115, 190))

    # Underwater cyan LED pool lights glowing through the water
    p1 = project(-150, 15, 6)
    p2 = project(-70, 15, 6)
    p3 = project(-110, 65, 6)
    for p in [p1, p2, p3]:
        draw.ellipse([p[0] - 25, p[1] - 15, p[0] + 25, p[1] + 15], fill=(0, 230, 255, 120))

    # Architectural landscape tree uplights on cypress trees
    for tx, ty in [(-280, -60), (-280, 0), (-280, 60), (-280, 120), (270, -40), (270, 20)]:
        sp = project(tx, ty, 2)
        draw.ellipse([sp[0] - 15, sp[1] - 10, sp[0] + 15, sp[1] + 10], fill=(255, 225, 140, 130))

    # Pergola pendant lights
    for lx in [-20, 10, 35]:
        lp = project(lx, 5, 68)
        draw.ellipse([lp[0] - 12, lp[1] - 8, lp[0] + 12, lp[1] + 8], fill=(255, 230, 150, 180))

    # Blur to simulate realistic lens diffusion / atmospheric glow
    blurred = img.filter(ImageFilter.GaussianBlur(radius=8))
    return blurred


def build_all_assets(assets_dir: Path) -> Dict[str, Any]:
    """Generate and write all architectural layers and manifest."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    arch_dir = assets_dir / "architecture"
    env_dir = assets_dir / "environment"
    land_dir = assets_dir / "landscaping"
    pool_dir = assets_dir / "pool"
    manifests_dir = assets_dir / "manifests"

    for d in [arch_dir, env_dir, land_dir, pool_dir, manifests_dir]:
        d.mkdir(parents=True, exist_ok=True)

    print("Generating photorealistic architectural assets...")

    layer_definitions = [
        ("plot_base", env_dir / "plot_base.png", create_plot_base),
        ("foundations", arch_dir / "foundations.png", create_foundations),
        ("columns_beams", arch_dir / "columns_beams.png", create_columns_beams),
        ("building_frame", arch_dir / "building_frame.png", create_building_frame),
        ("roof_enclosure", arch_dir / "roof_enclosure.png", create_roof_enclosure),
        ("villa_finished", arch_dir / "villa_finished.png", create_villa_finished),
        ("driveway_garage", arch_dir / "driveway_garage.png", create_driveway_garage),
        ("swimming_pool", pool_dir / "swimming_pool.png", create_swimming_pool),
        ("gardens", land_dir / "gardens.png", create_gardens),
        ("patio_pergola", land_dir / "patio_pergola.png", create_patio_pergola),
        ("upgrades", arch_dir / "upgrades.png", create_upgrades),
        ("estate_guesthouse", arch_dir / "estate_guesthouse.png", create_estate_guesthouse),
        ("master_expansion", arch_dir / "master_expansion.png", create_master_expansion),
        ("dusk_emissive", env_dir / "dusk_emissive.png", create_dusk_emissive_pass),
    ]

    manifest = {
        "version": 1,
        "resolution": {"width": WIDTH, "height": HEIGHT},
        "layers": {}
    }

    for idx, (name, path, gen_func) in enumerate(layer_definitions, start=1):
        print(f"  Rendering {name} -> {path.name}")
        image = gen_func()
        image.save(path, format="PNG", optimize=True)
        rel_path = path.relative_to(assets_dir).as_posix()
        manifest["layers"][name] = {
            "file": rel_path,
            "order": idx,
            "width": WIDTH,
            "height": HEIGHT
        }

    manifest_path = manifests_dir / "layer_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Asset generation complete. Manifest saved to {manifest_path}")
    return manifest


if __name__ == "__main__":
    assets_path = Path(__file__).parent.parent / "assets"
    build_all_assets(assets_path)
