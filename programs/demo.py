import sys

from rv32i import encode as insn, write_hex


if __name__ == "__main__":
    words = [
        insn("addi", 1, 0, 10),      # count down from 10
        insn("addi", 2, 0, 0),       # running sum
        insn("add", 2, 2, 1),        # loop:
        insn("addi", 1, 1, -1),
        insn("bne", 1, 0, -8),       # back to loop
        insn("sw", 2, 0, 0),
        insn("lw", 3, 0, 0),
        insn("addi", 4, 0, 0x100),   # result port
        insn("sw", 3, 0, 4),
        insn("jal", 0, 0),           # idle
    ]
    write_hex(sys.argv[1], words + [0] * (16 - len(words)))
