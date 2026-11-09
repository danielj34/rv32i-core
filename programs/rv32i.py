"""Encode RV32I instructions and write readmemh-compatible word images."""

from pathlib import Path

# Operand order follows assembly: rd, rs1, rs2; rd, rs1, imm;
# rd/rs2, offset, rs1 for memory; rs1, rs2, offset for branches.
ALU = {
    "add": (0, 0), "sub": (0, 0x20), "sll": (1, 0), "slt": (2, 0),
    "sltu": (3, 0), "xor": (4, 0), "srl": (5, 0), "sra": (5, 0x20),
    "or": (6, 0), "and": (7, 0),
}
IMMEDIATE = {"addi": 0, "slti": 2, "sltiu": 3, "xori": 4, "ori": 6, "andi": 7}
SHIFT = {"slli": (1, 0), "srli": (5, 0), "srai": (5, 0x20)}
LOAD = {"lb": 0, "lh": 1, "lw": 2, "lbu": 4, "lhu": 5}
STORE = {"sb": 0, "sh": 1, "sw": 2}
BRANCH = {"beq": 0, "bne": 1, "blt": 4, "bge": 5, "bltu": 6, "bgeu": 7}
SYSTEM = {"fence": 0x0FF0000F, "ecall": 0x00000073, "ebreak": 0x00100073}


def unsigned(value, width):
    if not 0 <= value < 1 << width:
        raise ValueError(f"{value} does not fit in {width} unsigned bits")
    return value


def signed(value, width):
    limit = 1 << (width - 1)
    if not -limit <= value < limit:
        raise ValueError(f"{value} does not fit in {width} signed bits")
    return value & ((1 << width) - 1)


def offset(value, width):
    if value % 2:
        raise ValueError(f"branch/jump offset must be even: {value}")
    return signed(value, width)


def register(value):
    return unsigned(value, 5)


def i_type(opcode, funct3, rd, rs1, imm_bits):
    return imm_bits << 20 | register(rs1) << 15 | funct3 << 12 | register(rd) << 7 | opcode


def encode(mnemonic, *operands):
    """Encode one instruction. U-type operands are the raw upper 20 bits."""
    if mnemonic in ALU:
        rd, rs1, rs2 = operands
        funct3, funct7 = ALU[mnemonic]
        return (funct7 << 25 | register(rs2) << 20 | register(rs1) << 15
                | funct3 << 12 | register(rd) << 7 | 0x33)
    if mnemonic in IMMEDIATE:
        rd, rs1, imm = operands
        return i_type(0x13, IMMEDIATE[mnemonic], rd, rs1, signed(imm, 12))
    if mnemonic in SHIFT:
        rd, rs1, shamt = operands
        funct3, funct7 = SHIFT[mnemonic]
        return i_type(0x13, funct3, rd, rs1, funct7 << 5 | unsigned(shamt, 5))
    if mnemonic in LOAD or mnemonic == "jalr":
        rd, imm, rs1 = operands
        opcode, funct3 = (0x67, 0) if mnemonic == "jalr" else (0x03, LOAD[mnemonic])
        return i_type(opcode, funct3, rd, rs1, signed(imm, 12))
    if mnemonic in STORE:
        rs2, imm, rs1 = operands
        bits = signed(imm, 12)
        return ((bits >> 5) << 25 | register(rs2) << 20 | register(rs1) << 15
                | STORE[mnemonic] << 12 | (bits & 31) << 7 | 0x23)
    if mnemonic in BRANCH:
        rs1, rs2, displacement = operands
        bits = offset(displacement, 13)
        return (((bits >> 12) & 1) << 31 | ((bits >> 5) & 63) << 25
                | register(rs2) << 20 | register(rs1) << 15 | BRANCH[mnemonic] << 12
                | ((bits >> 1) & 15) << 8 | ((bits >> 11) & 1) << 7 | 0x63)
    if mnemonic == "jal":
        rd, displacement = operands
        bits = offset(displacement, 21)
        return (((bits >> 20) & 1) << 31 | ((bits >> 1) & 1023) << 21
                | ((bits >> 11) & 1) << 20 | ((bits >> 12) & 255) << 12
                | register(rd) << 7 | 0x6F)
    if mnemonic in ("lui", "auipc"):
        rd, imm = operands
        opcode = 0x37 if mnemonic == "lui" else 0x17
        return unsigned(imm, 20) << 12 | register(rd) << 7 | opcode
    if mnemonic in SYSTEM:
        if operands:
            raise ValueError(f"{mnemonic} takes no operands")
        return SYSTEM[mnemonic]
    raise ValueError(f"unknown instruction: {mnemonic}")


def write_hex(path, words):
    Path(path).write_text("".join(f"{unsigned(word, 32):08x}\n" for word in words),
                          encoding="ascii")


def read_hex(path):
    return [int(line, 16) for line in Path(path).read_text(encoding="ascii").splitlines()]
