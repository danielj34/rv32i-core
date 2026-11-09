import operator
import random
from pathlib import Path

import cocotb
from cocotb.triggers import Timer

from rv32i import encode as insn, read_hex, write_hex

MASK = 0xFFFFFFFF


def signed(value):
    return value if value < 0x80000000 else value - (1 << 32)


class Machine:
    def __init__(self, dut):
        self.dut = dut

    async def boot(self, words, memory=None):
        self.memory = dict(memory or {})
        self.words = list(words)
        d = self.dut
        d.clk.value = 0
        d.reset.value = 1
        d.imem_rdata.value = insn("sw", 0, 0, 0)
        d.dmem_rdata.value = 0
        await Timer(5, unit="ns")
        assert int(d.dmem_wstrb.value) == 0
        assert int(d.retire_valid.value) == 0
        await self.rise()
        assert int(d.halted.value) == 0
        assert int(d.imem_addr.value) == 0

    async def rise(self):
        self.dut.clk.value = 1
        await Timer(5, unit="ns")

    async def prepare(self, pc):
        d = self.dut
        d.clk.value = 0
        d.reset.value = 0
        assert int(d.imem_addr.value) == pc, f"expected fetch at {pc:#x}"
        d.imem_rdata.value = self.words[pc // 4]
        await Timer(2, unit="ns")
        addr = int(d.dmem_addr.value)
        d.dmem_rdata.value = self.memory.get(addr, 0)
        await Timer(3, unit="ns")
        return addr

    async def step(self, pc, rd=0, value=0, *, load=None, store=None):
        d = self.dut
        addr = await self.prepare(pc)
        assert int(d.retire_valid.value) == 1, f"no retirement at {pc:#x}"
        actual = int(d.retire_rd.value), int(d.retire_wdata.value)
        assert actual == (rd, value & MASK), f"writeback at {pc:#x}: {actual}"
        assert int(d.dmem_read.value) == (load is not None)
        if load is not None:
            assert addr == load
        if store is None:
            assert int(d.dmem_wstrb.value) == 0
        else:
            expected_addr, strobe, data = store
            assert addr == expected_addr
            assert int(d.dmem_wstrb.value) == strobe
            lanes = sum(0xFF << (8 * i) for i in range(4) if strobe & (1 << i))
            assert int(d.dmem_wdata.value) & lanes == data
            self.memory[addr] = (self.memory.get(addr, 0) & ~lanes) | data
        await self.rise()
        assert int(d.halted.value) == 0

    async def trap(self, pc, cause):
        d = self.dut
        await self.prepare(pc)
        assert int(d.retire_valid.value) == 0
        assert int(d.retire_rd.value) == 0
        assert int(d.dmem_wstrb.value) == 0
        assert int(d.dmem_read.value) == 0
        await self.rise()
        assert int(d.halted.value) == 1
        assert int(d.trap_cause.value) == cause
        assert int(d.imem_addr.value) == pc

        # Replacing the faulting word must still leave the machine halted.
        d.clk.value = 0
        d.imem_rdata.value = insn("sw", 0, 0, 0)
        await Timer(5, unit="ns")
        assert int(d.retire_valid.value) == 0
        assert int(d.dmem_wstrb.value) == 0
        await self.rise()
        assert int(d.imem_addr.value) == pc
        assert int(d.trap_cause.value) == cause


@cocotb.test()
async def integer_alu(dut):
    m = Machine(dut)
    cases = [
        (insn("addi", 0, 0, -1), 0, 0),
        (insn("addi", 31, 0, -1), 31, -1),
        (insn("addi", 1, 31, 1), 1, 0),
        (insn("lui", 1, 0x80000), 1, 0x80000000),
        (insn("auipc", 2, 0xFFFFF), 2, 16 - 4096),
        (insn("slti", 3, 1, -1), 3, 1),
        (insn("sltiu", 4, 1, -1), 4, 1),
        (insn("xori", 5, 31, -1), 5, 0),
        (insn("ori", 6, 1, 1), 6, 0x80000001),
        (insn("andi", 7, 6, 7), 7, 1),
        (insn("slli", 8, 7, 31), 8, 0x80000000),
        (insn("srli", 9, 8, 31), 9, 1),
        (insn("srai", 10, 8, 31), 10, -1),
        (insn("fence"), 0, 0),
    ]
    functions = {
        "add": operator.add, "sub": operator.sub, "xor": operator.xor,
        "or": operator.or_, "and": operator.and_, "sltu": operator.lt,
        "slt": lambda a, b: signed(a) < signed(b),
        "sll": lambda a, b: a << (b & 31),
        "srl": lambda a, b: a >> (b & 31),
        "sra": lambda a, b: signed(a) >> (b & 31),
    }
    rng = random.Random(32)
    pairs = [(0, 0), (MASK, 1), (0x80000000, MASK), (0x7FFFFFFF, 1)]
    pairs += [(rng.getrandbits(32), rng.getrandbits(32)) for _ in range(20)]
    for a, b in pairs:
        for reg, n in [(1, a), (2, b)]:
            upper = ((n + 0x800) >> 12) & 0xFFFFF
            low = ((n + 0x800) & 0xFFF) - 0x800
            cases += [
                (insn("lui", reg, upper), reg, upper << 12),
                (insn("addi", reg, reg, low), reg, n),
            ]
        for mnemonic, operation in functions.items():
            cases.append((insn(mnemonic, 3, 1, 2), 3, operation(a, b)))

    image = Path("build/alu.hex")
    write_hex(image, [word for word, _, _ in cases])
    await m.boot(read_hex(image))
    for i, (_, rd, value) in enumerate(cases):
        await m.step(4 * i, rd, value)


@cocotb.test()
async def byte_lanes_and_load_extension(dut):
    m = Machine(dut)
    await m.boot([
        insn("addi", 1, 0, 0x44),
        insn("lb", 2, -4, 1),
        insn("lb", 3, -3, 1),
        insn("lbu", 4, -2, 1),
        insn("lh", 5, -2, 1),
        insn("lhu", 6, -2, 1),
        insn("lw", 0, -4, 1),
        insn("sb", 4, -1, 1),
        insn("sh", 6, -4, 1),
        insn("lw", 7, -4, 1),
        insn("sw", 7, 0, 1),
        insn("lw", 8, 0, 1),
        insn("sb", 0, -4, 1),
        insn("sb", 0, -3, 1),
        insn("sb", 0, -2, 1),
        insn("sh", 0, -2, 1),
        insn("lw", 9, -4, 1),
    ], {0x40: 0xFE80AA7F, 0x44: MASK})
    await m.step(0, 1, 0x44)
    for i, value in enumerate([127, -86, 128, -384, 0xFE80], 1):
        await m.step(i * 4, i + 1, value, load=0x40)
    await m.step(24, load=0x40)
    await m.step(28, store=(0x40, 0b1000, 0x80000000))
    await m.step(32, store=(0x40, 0b0011, 0xFE80))
    await m.step(36, 7, 0x8080FE80, load=0x40)
    await m.step(40, store=(0x44, 0b1111, 0x8080FE80))
    await m.step(44, 8, 0x8080FE80, load=0x44)
    await m.step(48, store=(0x40, 0b0001, 0))
    await m.step(52, store=(0x40, 0b0010, 0))
    await m.step(56, store=(0x40, 0b0100, 0))
    await m.step(60, store=(0x40, 0b1100, 0))
    await m.step(64, 9, 0, load=0x40)


@cocotb.test()
async def branch_comparisons(dut):
    m = Machine(dut)
    branches = [
        ("beq", 0, 0, True), ("beq", 1, 0, False),
        ("bne", 1, 0, True), ("bne", 0, 0, False),
        ("blt", 1, 0, True), ("blt", 0, 1, False),
        ("bge", 0, 1, True), ("bge", 1, 0, False),
        ("bltu", 0, 1, True), ("bltu", 1, 0, False),
        ("bgeu", 1, 0, True), ("bgeu", 0, 1, False),
    ]
    words = [insn("addi", 1, 0, -1)]
    for op, rs1, rs2, taken in branches:
        words += [insn(op, rs1, rs2, 8), 0 if taken else insn("addi", 2, 0, 5)]
    words.append(insn("ebreak"))
    await m.boot(words)
    await m.step(0, 1, -1)
    for i, (_, _, _, taken) in enumerate(branches):
        pc = 4 + 8 * i
        await m.step(pc)
        if not taken:
            await m.step(pc + 4, 2, 5)
    await m.trap(4 + 8 * len(branches), 3)


@cocotb.test()
async def jumps_and_backwards_branch(dut):
    m = Machine(dut)
    await m.boot([
        insn("addi", 1, 0, 2),       # 0
        insn("addi", 1, 1, -1),      # 4
        insn("bne", 1, 0, -4),       # 8
        insn("jal", 5, 12),          # 12 -> 24; link = 16
        insn("jal", 0, 24),          # 16 -> 40
        0,
        insn("addi", 5, 5, 1),       # 24
        insn("jalr", 5, 0, 5),       # 28 -> 16 (17 & ~1); link = 32
        0,
        insn("ebreak"),              # 36
        insn("jal", 6, -4),          # 40 -> 36; link = 44
    ])
    for pc, rd, value in [
        (0, 1, 2), (4, 1, 1), (8, 0, 0), (4, 1, 0), (8, 0, 0),
        (12, 5, 16), (24, 5, 17), (28, 5, 32), (16, 0, 0), (40, 6, 44),
    ]:
        await m.step(pc, rd, value)
    await m.trap(36, 3)


@cocotb.test()
async def precise_traps_and_reset(dut):
    m = Machine(dut)
    for word, cause in [
        (insn("jal", 1, 2), 0),
        (insn("jalr", 1, 3, 0), 0),
        (insn("beq", 0, 0, 2), 0),
        (insn("lh", 1, 1, 0), 4),
        (insn("lw", 0, 2, 0), 4),
        (insn("sh", 1, 3, 0), 6),
        (insn("sw", 1, 1, 0), 6),
        (insn("ecall"), 8),
        (0x02000033, 2),  # MUL requires M
        (0x02001013, 2),  # reserved SLLI encoding
        (0x0000100F, 2),  # FENCE.I requires Zifencei
        (0x00003003, 2),  # reserved load width
        (0, 2),
    ]:
        await m.boot([insn("addi", 1, 0, 7), word])
        await m.step(0, 1, 7)
        await m.trap(4, cause)
    await m.boot([insn("bne", 0, 0, 2), insn("addi", 2, 1, 0)])
    await m.step(0)
    await m.step(4, 2, 0)
