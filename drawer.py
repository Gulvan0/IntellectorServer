from PIL import Image, ImageDraw, ImageFont

from math import sqrt

from rules import HexCoordinates, Piece, PieceColor, PieceKind, Position

SQRT3 = sqrt(3)

DIMENSIONS = (1920, 1080)

SIDE = min(DIMENSIONS[0] / 14, DIMENSIONS[1] / 7 / SQRT3)
WIDTH = 2 * SIDE
HEIGHT = SQRT3 * SIDE
HALF_HEIGHT = HEIGHT / 2

X_OFFSET = (DIMENSIONS[0] - SIDE * 14) / 2
Y_OFFSET = (DIMENSIONS[1] - HEIGHT * 7) / 2

PIECES: dict[Piece, Image] = {}
for kind in PieceKind:
    for color in PieceColor:
        PIECES[Piece(kind, color)] = Image.open(f'pieces/{kind}{color}.png')

def get_hex_center(coords: HexCoordinates) -> tuple[float, float]:
    return coords.i * SIDE * 1.5 + SIDE + X_OFFSET, (coords.j + (1 if coords.i % 2 == 1 else 0.5)) * HEIGHT + Y_OFFSET

def get_hex_vertices(coords: HexCoordinates) -> list[tuple[float, float]]:
    top_left_vertices = [
        (0, HALF_HEIGHT),
        (0.5 * SIDE, 0),
        (1.5 * SIDE, 0),
        (WIDTH, HALF_HEIGHT),
        (1.5 * SIDE, HEIGHT),
        (0.5 * SIDE, HEIGHT),
    ]
    y_addend = HALF_HEIGHT if coords.i % 2 == 1 else 0
    return [
        (vertex[0] + 1.5 * SIDE * coords.i + X_OFFSET, vertex[1] + HEIGHT * coords.j + y_addend + Y_OFFSET)
        for vertex in top_left_vertices
    ]

im = Image.new('RGB', DIMENSIONS, 'white')
draw = ImageDraw.Draw(im)

for i in range(0, 9):
    for j in range(0, 7):
        if j == 6 and i % 2 == 1:
            continue
        vertices = get_hex_vertices(HexCoordinates(i, j))
        draw.polygon(xy=vertices, fill="#d18b47" if j % 3 == i % 2 else "#ffcf9f", outline="#664126", width=6)

def mark_hex(coords: HexCoordinates):
    draw.circle(xy=get_hex_center(coords), radius=10, fill="red")

def draw_arrow(departure: HexCoordinates, destination: HexCoordinates, colour: str | None = None, spread: float = 0):
    dep_center = get_hex_center(departure)
    dest_center = get_hex_center(destination)
    fp = (dep_center[0] + (random() - 0.5) * spread, dep_center[1] + (random() - 0.5) * spread)
    sp = (dest_center[0] + (random() - 0.5) * spread, dest_center[1] + (random() - 0.5) * spread)
    draw.line(xy=[fp, sp], width=5, fill=colour or "blue")
    draw.circle(xy=sp, radius=10, fill=colour or "blue")

def put_piece(piece:Piece, coords: HexCoordinates):
    center = get_hex_center(coords)
    piece_image: Image = PIECES[piece]
    im.paste(piece_image, (round(center[0] - piece_image.width / 2), round(center[1] - piece_image.height / 2)), piece_image)

ALL_COLORS = [
    "AliceBlue",
    "AntiqueWhite",
    "Aqua",
    "Aquamarine",
    "Azure",
    "Beige",
    "Bisque",
    "Black",
    "BlanchedAlmond",
    "Blue",
    "BlueViolet",
    "Brown",
    "BurlyWood",
    "CadetBlue",
    "Chartreuse",
    "Chocolate",
    "Coral",
    "CornflowerBlue",
    "Cornsilk",
    "Crimson",
    "Cyan",
    "DarkBlue",
    "DarkCyan",
    "DarkGoldenRod",
    "DarkGray",
    "DarkGrey",
    "DarkGreen",
    "DarkKhaki",
    "DarkMagenta",
    "DarkOliveGreen",
    "DarkOrange",
    "DarkOrchid",
    "DarkRed",
    "DarkSalmon",
    "DarkSeaGreen",
    "DarkSlateBlue",
    "DarkSlateGray",
    "DarkSlateGrey",
    "DarkTurquoise",
    "DarkViolet",
    "DeepPink",
    "DeepSkyBlue",
    "DimGray",
    "DimGrey",
    "DodgerBlue",
    "FireBrick",
    "FloralWhite",
    "ForestGreen",
    "Fuchsia",
    "Gainsboro",
    "GhostWhite",
    "Gold",
    "GoldenRod",
    "Gray",
    "Grey",
    "Green",
    "GreenYellow",
    "HoneyDew",
    "HotPink",
    "IndianRed",
    "Indigo",
    "Ivory",
    "Khaki",
    "Lavender",
    "LavenderBlush",
    "LawnGreen",
    "LemonChiffon",
    "LightBlue",
    "LightCoral",
    "LightCyan",
    "LightGoldenRodYellow",
    "LightGray",
    "LightGrey",
    "LightGreen",
    "LightPink",
    "LightSalmon",
    "LightSeaGreen",
    "LightSkyBlue",
    "LightSlateGray",
    "LightSlateGrey",
    "LightSteelBlue",
    "LightYellow",
    "Lime",
    "LimeGreen",
    "Linen",
    "Magenta",
    "Maroon",
    "MediumAquaMarine",
    "MediumBlue",
    "MediumOrchid",
    "MediumPurple",
    "MediumSeaGreen",
    "MediumSlateBlue",
    "MediumSpringGreen",
    "MediumTurquoise",
    "MediumVioletRed",
    "MidnightBlue",
    "MintCream",
    "MistyRose",
    "Moccasin",
    "NavajoWhite",
    "Navy",
    "OldLace",
    "Olive",
    "OliveDrab",
    "Orange",
    "OrangeRed",
    "Orchid",
    "PaleGoldenRod",
    "PaleGreen",
    "PaleTurquoise",
    "PaleVioletRed",
    "PapayaWhip",
    "PeachPuff",
    "Peru",
    "Pink",
    "Plum",
    "PowderBlue",
    "Purple",
    "RebeccaPurple",
    "Red",
    "RosyBrown",
    "RoyalBlue",
    "SaddleBrown",
    "Salmon",
    "SandyBrown",
    "SeaGreen",
    "SeaShell",
    "Sienna",
    "Silver",
    "SkyBlue",
    "SlateBlue",
    "SlateGray",
    "SlateGrey",
    "Snow",
    "SpringGreen",
    "SteelBlue",
    "Tan",
    "Teal",
    "Thistle",
    "Tomato",
    "Turquoise",
    "Violet",
    "Wheat",
    "White",
    "WhiteSmoke",
    "Yellow",
    "YellowGreen",
]

# mark_hex(HexCoordinates(1, 2))
for coords, piece in Position.default_starting().piece_arrangement.items():
    put_piece(piece, coords)
from random import randint, random
for ply in Position.default_starting().available_plys():
    draw_arrow(ply.departure, ply.destination, ALL_COLORS[randint(0, len(ALL_COLORS) - 1)], 60)
    dest_center = get_hex_center(ply.destination)
    draw.text(dest_center, str(ply.destination.scalar), (0, 0, 0), font=ImageFont.load_default(30))

im.show()