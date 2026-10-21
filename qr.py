"""A QR code, drawn here rather than by a program that may not be
installed.

Why this file exists: the browser already offered "show this as a QR
code", and it did it by shelling out to `qrencode`. On a machine
without that program the feature was simply dead -- and a Wi-Fi
password or a login you want to get onto a phone is exactly the kind
of thing you need when the machine is not the one you set up. This is
the encoder, in the standard library and nothing else, so the feature
works everywhere the browser does.

What it does: byte mode (so any text, UTF-8), versions 1 to 10, error
correction level M with a fall back to L for text that would not
otherwise fit, the full eight masks scored the way the standard says,
and the proper format and version information. That is up to 271
bytes at level M -- a long password, a wifi: string, an otpauth:// URL
with room to spare.

What it does not do: Kanji and alphanumeric modes (byte mode encodes
the same text, just less densely), versions above 10, and reading a
code back. ISO/IEC 18004 is the reference for all of it.
"""

#: total codewords, and the data block layout per (version, level):
#: (ec codewords per block, [(blocks, data codewords per block), ...])
TOTAL = {1: 26, 2: 44, 3: 70, 4: 100, 5: 134,
         6: 172, 7: 196, 8: 242, 9: 292, 10: 346}

BLOCKS = {
    (1, "L"): (7, [(1, 19)]),            (1, "M"): (10, [(1, 16)]),
    (2, "L"): (10, [(1, 34)]),           (2, "M"): (16, [(1, 28)]),
    (3, "L"): (15, [(1, 55)]),           (3, "M"): (26, [(1, 44)]),
    (4, "L"): (20, [(1, 80)]),           (4, "M"): (18, [(2, 32)]),
    (5, "L"): (26, [(1, 108)]),          (5, "M"): (24, [(2, 43)]),
    (6, "L"): (18, [(2, 68)]),           (6, "M"): (16, [(4, 27)]),
    (7, "L"): (20, [(2, 78)]),           (7, "M"): (18, [(4, 31)]),
    (8, "L"): (24, [(2, 97)]),           (8, "M"): (22, [(2, 38), (2, 39)]),
    (9, "L"): (30, [(2, 116)]),          (9, "M"): (22, [(3, 36), (2, 37)]),
    (10, "L"): (18, [(2, 68), (2, 69)]), (10, "M"): (26, [(4, 43), (1, 44)]),
}

#: where the alignment squares sit, by version (none in version 1)
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
         6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46],
         10: [6, 28, 50]}

#: the 18 bits of version information, for versions 7 and up
VERSION_BITS = {7: 0x07C94, 8: 0x085BC, 9: 0x09A99, 10: 0x0A4D3}

#: level bits as they go into the format information
LEVEL_BITS = {"L": 0b01, "M": 0b00, "Q": 0b11, "H": 0b10}


# ---- the field the error correction lives in ----------------------
def _tables():
    """log and antilog for GF(256) with the QR generator 0x11d."""
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


EXP, LOG = _tables()


def _mul(a, b):
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]


def _generator(degree):
    """The generator polynomial for that many error correction bytes."""
    poly = [1]
    for i in range(degree):
        poly = _poly_mul(poly, [1, EXP[i]])
    return poly


def _poly_mul(a, b):
    out = [0] * (len(a) + len(b) - 1)
    for i, one in enumerate(a):
        for j, two in enumerate(b):
            out[i + j] ^= _mul(one, two)
    return out


def ec_bytes(data, count):
    """The error correction codewords for one block."""
    gen = _generator(count)
    rest = list(data) + [0] * count
    for i in range(len(data)):
        factor = rest[i]
        if factor:
            for j, coefficient in enumerate(gen):
                rest[i + j] ^= _mul(coefficient, factor)
    return rest[len(data):]


# ---- the bit stream ------------------------------------------------
def _fit(length, want_level=None):
    """The smallest version and level that holds this many bytes.

    Level M unless it will not fit, then L: more error correction is
    better right up to the point where it means a bigger code, and a
    bigger code on a phone screen is harder to read, not easier.
    """
    for level in ([want_level] if want_level else ["M", "L"]):
        for version in range(1, 11):
            ec, groups = BLOCKS[(version, level)]
            data_codewords = sum(blocks * size for blocks, size in groups)
            counter = 8 if version <= 9 else 16
            if 4 + counter + 8 * length <= data_codewords * 8:
                return version, level, data_codewords
    raise ValueError("too long for a version 1-10 QR code")


def codewords(text, want_level=None):
    """The data codewords, interleaved with their error correction,
    ready to go into the grid."""
    raw = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    version, level, data_codewords = _fit(len(raw), want_level)
    counter = 8 if version <= 9 else 16

    bits = []

    def push(value, width):
        for shift in range(width - 1, -1, -1):
            bits.append((value >> shift) & 1)

    push(0b0100, 4)                 # byte mode
    push(len(raw), counter)
    for byte in raw:
        push(byte, 8)
    # the terminator, up to four zero bits, then pad to a whole byte
    for _ in range(min(4, data_codewords * 8 - len(bits))):
        bits.append(0)
    while len(bits) % 8:
        bits.append(0)
    data = bytearray(int("".join(str(b) for b in bits[i:i + 8]), 2)
                     for i in range(0, len(bits), 8))
    # and the two pad codewords, alternating, for the rest
    pads = (0xEC, 0x11)
    while len(data) < data_codewords:
        data.append(pads[(len(data) - len(bits) // 8) % 2])

    ec_count, groups = BLOCKS[(version, level)]
    blocks, parities = [], []
    at = 0
    for count, size in groups:
        for _ in range(count):
            chunk = bytes(data[at:at + size])
            at += size
            blocks.append(chunk)
            parities.append(ec_bytes(chunk, ec_count))

    out = []
    for i in range(max(len(b) for b in blocks)):
        for block in blocks:
            if i < len(block):
                out.append(block[i])
    for i in range(ec_count):
        for parity in parities:
            out.append(parity[i])
    return out, version, level


# ---- the grid ------------------------------------------------------
def _blank(size):
    return [[None] * size for _ in range(size)]


def _finder(grid, row, col):
    for dr in range(-1, 8):
        for dc in range(-1, 8):
            r, c = row + dr, col + dc
            if not (0 <= r < len(grid) and 0 <= c < len(grid)):
                continue
            inside = 0 <= dr <= 6 and 0 <= dc <= 6
            dark = inside and (dr in (0, 6) or dc in (0, 6)
                               or (2 <= dr <= 4 and 2 <= dc <= 4))
            grid[r][c] = 1 if dark else 0


def _reserve(grid, version):
    size = len(grid)
    for row, col in ((0, 0), (0, size - 7), (size - 7, 0)):
        _finder(grid, row, col)
    for i in range(8, size - 8):            # the timing lines
        grid[6][i] = 1 if i % 2 == 0 else 0
        grid[i][6] = 1 if i % 2 == 0 else 0
    for row in ALIGN[version]:              # the alignment squares
        for col in ALIGN[version]:
            if grid[row][col] is not None:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    dark = max(abs(dr), abs(dc)) != 1
                    grid[row + dr][col + dc] = 1 if dark else 0
    grid[size - 8][8] = 1                   # the one always-dark module
    for i in range(9):                      # format information
        if grid[8][i] is None:
            grid[8][i] = 0
        if grid[i][8] is None:
            grid[i][8] = 0
    for i in range(8):
        grid[8][size - 1 - i] = 0
        grid[size - 1 - i][8] = 0
    if version >= 7:                        # version information
        for i in range(6):
            for j in range(3):
                grid[size - 11 + j][i] = 0
                grid[i][size - 11 + j] = 0
    return grid


def _free(grid, version):
    """Which modules the data may use: everything the patterns above
    did not claim."""
    size = len(grid)
    taken = _reserve(_blank(size), version)
    return [[taken[r][c] is None for c in range(size)] for r in range(size)]


def _place(grid, free, data):
    """The zigzag: two columns at a time, right to left, upwards then
    downwards, skipping the timing column."""
    size = len(grid)
    bits = []
    for byte in data:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)
    at = 0
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1                       # the vertical timing line
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for c in (col, col - 1):
                if not free[row][c]:
                    continue
                grid[row][c] = bits[at] if at < len(bits) else 0
                at += 1
        upward = not upward
        col -= 2
    return grid


def _mask_bit(mask, row, col):
    if mask == 0:
        return (row + col) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return col % 3 == 0
    if mask == 3:
        return (row + col) % 3 == 0
    if mask == 4:
        return (row // 2 + col // 3) % 2 == 0
    if mask == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if mask == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    return ((row + col) % 2 + (row * col) % 3) % 2 == 0


def _bch(value, generator, width):
    rest = value
    while rest.bit_length() - 1 >= width:
        rest ^= generator << (rest.bit_length() - generator.bit_length())
    return rest


def format_bits(level, mask):
    """The 15 bits of format information, BCH(15,5) and then the
    standard mask, which is what stops an all-zero format from looking
    like a blank area."""
    value = (LEVEL_BITS[level] << 3) | mask
    bits = (value << 10) | _bch(value << 10, 0b10100110111, 10)
    return bits ^ 0b101010000010010


def _write_format(grid, level, mask):
    size = len(grid)
    bits = format_bits(level, mask)
    for i in range(15):
        bit = (bits >> i) & 1
        # the copy around the top-left finder
        if i < 6:
            grid[8][i] = bit
        elif i == 6:
            grid[8][7] = bit
        elif i == 7:
            grid[8][8] = bit
        elif i == 8:
            grid[7][8] = bit
        else:
            grid[14 - i][8] = bit
        # and the second copy, split across the other two corners
        if i < 8:
            grid[8][size - 1 - i] = bit
        else:
            grid[size - 15 + i][8] = bit
    grid[size - 8][8] = 1
    return grid


def _write_version(grid, version):
    if version < 7:
        return grid
    size = len(grid)
    bits = VERSION_BITS[version]
    for i in range(18):
        bit = (bits >> i) & 1
        grid[size - 11 + i % 3][i // 3] = bit
        grid[i // 3][size - 11 + i % 3] = bit
    return grid


def _penalty(grid):
    """The four penalties of the standard, added up. The mask with the
    lowest total is the one that goes out."""
    size = len(grid)
    score = 0

    # 1: runs of five or more of the same colour
    for line in list(grid) + [list(col) for col in zip(*grid)]:
        run, last = 1, line[0]
        for cell in line[1:]:
            if cell == last:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run, last = 1, cell
        if run >= 5:
            score += 3 + (run - 5)

    # 2: any 2x2 of one colour
    for row in range(size - 1):
        for col in range(size - 1):
            here = grid[row][col]
            if (grid[row][col + 1] == here and grid[row + 1][col] == here
                    and grid[row + 1][col + 1] == here):
                score += 3

    # 3: the finder-like pattern, in either direction
    want = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    back = list(reversed(want))
    for line in list(grid) + [list(col) for col in zip(*grid)]:
        for i in range(size - 10):
            window = line[i:i + 11]
            if window == want or window == back:
                score += 40

    # 4: how far from half dark the whole thing is
    dark = sum(sum(row) for row in grid)
    percent = dark * 100 // (size * size)
    score += 10 * (abs(percent - 50) // 5)
    return score


def matrix(text, level=None):
    """The finished grid: a list of rows of 0 and 1, no quiet zone.

    Every mask is drawn and scored and the best one is kept, which is
    what the standard asks for and what makes the difference between a
    code a phone reads at once and one it has to be coaxed into.
    """
    data, version, level = codewords(text, level)
    size = 17 + 4 * version
    free = _free(_blank(size), version)

    best, best_score = None, None
    for mask in range(8):
        grid = _reserve(_blank(size), version)
        _place(grid, free, data)
        for row in range(size):
            for col in range(size):
                if free[row][col] and _mask_bit(mask, row, col):
                    grid[row][col] ^= 1
        _write_format(grid, level, mask)
        _write_version(grid, version)
        grid = [[int(cell or 0) for cell in row] for row in grid]
        score = _penalty(grid)
        if best_score is None or score < best_score:
            best, best_score = grid, score
    return best


def as_text(grid, dark="██", light="  ", quiet=2):
    """The grid as something you can look at in a terminal."""
    size = len(grid)
    blank = light * (size + quiet * 2)
    rows = [blank for _ in range(quiet)]
    for row in grid:
        rows.append(light * quiet
                    + "".join(dark if cell else light for cell in row)
                    + light * quiet)
    rows.extend(blank for _ in range(quiet))
    return "\n".join(rows)

# ---- reading one back ----------------------------------------------
# The other direction, for "read the QR code in this picture". It is
# the encoder's own tables run backwards, which is why it lives here:
# every structure it needs -- the block layout, the mask patterns, the
# reserved modules, the zigzag -- is already written above, and a second
# copy of any of them would be a second thing to keep right.
#
# What it reads: an upright code, any module size, with or without a
# quiet zone, versions 1 to 10, levels L and M (which is what matrix()
# writes), byte and numeric and alphanumeric modes. What it does not:
# rotation, perspective, or error correction -- the parity is checked
# and a code that does not come back clean says so rather than guessing.


def _syndromes_zero(block, ec_count):
    """Whether a block's parity checks out.

    The Reed-Solomon syndromes of a codeword are zero exactly when the
    codeword is undamaged; computing them needs only the log tables the
    encoder already builds, and it is the honest way to say "this is
    what the code says" rather than "this is roughly what it says"."""
    exp, log = _tables()
    for i in range(ec_count):
        total = 0
        for byte in block:
            total = _mul(total, exp[i % 255]) ^ byte
        if total:
            return False
    return True


def _unmask(grid, mask):
    """The data modules with the mask taken off."""
    size = len(grid)
    out = [row[:] for row in grid]
    version = (size - 17) // 4
    free = _free(_blank(size), version)
    for row in range(size):
        for col in range(size):
            if free[row][col] and _mask_bit(mask, row, col):
                out[row][col] ^= 1
    return out


def _read_format(grid):
    """The level and the mask, from the format information.

    Both copies are tried, and each candidate is checked against the
    fifteen-bit BCH code the encoder writes -- so a smudged corner
    falls back to the other copy instead of producing a plausible
    wrong answer."""
    size = len(grid)
    first = [grid[8][c] for c in (0, 1, 2, 3, 4, 5, 7, 8)] + \
            [grid[7][8], grid[5][8], grid[4][8], grid[3][8],
             grid[2][8], grid[1][8], grid[0][8]]
    second = [grid[size - 1 - i][8] for i in range(7)] + \
             [grid[8][size - 8 + i] for i in range(8)]
    for bits in (first, second):
        value = 0
        for bit in bits:
            value = (value << 1) | (bit or 0)
        for level in ("L", "M", "Q", "H"):
            for mask in range(8):
                try:
                    if format_bits(level, mask) == value:
                        return level, mask
                except KeyError:
                    continue
    return "", -1


def _read_codewords(grid):
    """The zigzag, read rather than written."""
    size = len(grid)
    version = (size - 17) // 4
    free = _free(_blank(size), version)
    bits = []
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for c in (col, col - 1):
                if free[row][c]:
                    bits.append(grid[row][c] or 0)
        upward = not upward
        col -= 2
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        value = 0
        for bit in bits[i:i + 8]:
            value = (value << 1) | bit
        out.append(value)
    return bytes(out)


def _deinterleave(stream, version, level):
    """The blocks put back the way they were, and their parity
    checked."""
    ec_count, groups = BLOCKS[(version, level)]
    sizes = []
    for count, size in groups:
        sizes.extend([size] * count)
    blocks = [bytearray() for _ in sizes]
    at = 0
    for i in range(max(sizes)):
        for n, size in enumerate(sizes):
            if i < size:
                if at >= len(stream):
                    return None
                blocks[n].append(stream[at])
                at += 1
    parities = [bytearray() for _ in sizes]
    for _i in range(ec_count):
        for n in range(len(sizes)):
            if at >= len(stream):
                return None
            parities[n].append(stream[at])
            at += 1
    for block, parity in zip(blocks, parities):
        if not _syndromes_zero(bytes(block) + bytes(parity), ec_count):
            return None
    return b"".join(bytes(b) for b in blocks)


#: the forty-five characters of alphanumeric mode, in order
ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"


def _read_payload(data, version):
    """The data codewords as the text they carry."""
    bits = []
    for byte in data:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)
    at = 0

    def take(width):
        nonlocal at
        value = 0
        for _ in range(width):
            if at >= len(bits):
                raise ValueError("ran out of bits")
            value = (value << 1) | bits[at]
            at += 1
        return value

    out = []
    while at + 4 <= len(bits):
        mode = take(4)
        if mode == 0:                       # the terminator
            break
        if mode == 0b0100:                  # byte
            count = take(8 if version <= 9 else 16)
            raw = bytearray()
            for _ in range(count):
                raw.append(take(8))
            out.append(bytes(raw).decode("utf-8", "replace"))
        elif mode == 0b0001:                # numeric
            count = take(10 if version <= 9 else 12)
            text = []
            while count >= 3:
                text.append("%03d" % take(10))
                count -= 3
            if count == 2:
                text.append("%02d" % take(7))
            elif count == 1:
                text.append("%d" % take(4))
            out.append("".join(text))
        elif mode == 0b0010:                # alphanumeric
            count = take(9 if version <= 9 else 11)
            text = []
            while count >= 2:
                pair = take(11)
                text.append(ALNUM[pair // 45] + ALNUM[pair % 45])
                count -= 2
            if count:
                text.append(ALNUM[take(6)])
            out.append("".join(text))
        else:
            break
    return "".join(out)


def read_matrix(grid):
    """A module grid as the text it carries, or "" when it is not a
    code this can read."""
    size = len(grid)
    if size < 21 or (size - 17) % 4 or (size - 17) // 4 > 10:
        return ""
    version = (size - 17) // 4
    level, mask = _read_format(grid)
    if mask < 0 or (version, level) not in BLOCKS:
        return ""
    stream = _read_codewords(_unmask(grid, mask))
    data = _deinterleave(stream, version, level)
    if data is None:
        return ""
    try:
        return _read_payload(data, version)
    except (ValueError, IndexError, UnicodeDecodeError):
        return ""


def grid_from_pixels(dark, width, height):
    """A module grid out of a picture.

    `dark(x, y)` says whether that pixel is dark. The picture is
    expected to hold one upright code: the quiet zone is trimmed by
    finding the dark bounding box, and the module size is taken from
    the top-left finder pattern, which is seven modules wide by
    definition. That is enough for a code on a web page, which is what
    this is for -- a photograph at an angle is a different problem and
    is not pretended to be solved."""
    left, top, right, bottom = width, height, -1, -1
    for y in range(height):
        for x in range(width):
            if dark(x, y):
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)
    if right < left or bottom < top:
        return []
    span = min(right - left + 1, bottom - top + 1)
    # the finder pattern's seven modules, measured along the top edge
    run = 0
    y = top
    while y <= bottom and not dark(left, y):
        y += 1
    x = left
    while x <= right and dark(x, y):
        run += 1
        x += 1
    if run < 7:
        return []
    module = run / 7.0
    size = int(round(span / module))
    if size < 21 or (size - 17) % 4:
        # the span is the better measurement when the module size is
        # fractional: snap to the nearest legal grid
        best = None
        for candidate in range(21, 58, 4):
            guess = abs(span / candidate - module)
            if best is None or guess < best[0]:
                best = (guess, candidate)
        size = best[1]
    step = span / float(size)
    grid = []
    for row in range(size):
        line = []
        for col in range(size):
            x = int(left + (col + 0.5) * step)
            y = int(top + (row + 0.5) * step)
            line.append(1 if dark(min(x, width - 1),
                                  min(y, height - 1)) else 0)
        grid.append(line)
    return grid


def read_pixels(dark, width, height):
    """A picture as the text its QR code carries."""
    grid = grid_from_pixels(dark, width, height)
    return read_matrix(grid) if grid else ""
