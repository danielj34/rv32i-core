# Single-cycle RV32I core

A 32-bit RISC-V core in SystemVerilog with separate instruction and data ports. Every instruction that completes commits on the next rising edge. The iCEBreaker demo runs a loop that adds the integers 1 through 10, writes the sum to scratch memory, then reads it back and sends it to a memory-mapped result port.

## Run locally

Use Python 3.13, Verilator 5.036 or newer, GNU Make, and a C++ compiler.

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
make lint
make test
```

The cocotb testbench checks the fetch address, register writeback and memory strobes cycle by cycle. It covers all RV32I instruction families, including signed and unsigned comparisons, the four store byte lanes, taken and untaken branches, JAL/JALR targets and link addresses, and precise traps. Register-register ALU checks use a fixed seed for reproducibility. A separate test runs the FPGA demo through power-on reset and a button reset.

The encoder in [programs/rv32i.py](programs/rv32i.py) produces 32-bit instruction words. For example, run this from the repository root to create a two-word image.

```python
from programs.rv32i import encode, write_hex

write_hex("example.hex", [encode("addi", 1, 0, 42), encode("ebreak")])
```

`make test` generates `build/alu.hex` and `build/demo.hex`. Each line contains one word in instruction address order. Line 1 maps to the reset vector.

## Datapath and memory interface

```text
PC ──► instruction ROM ──► decode ──► register file reads
 ▲                           │                  │
 │                      immediate               ▼
 │                           └───────────────► ALU / address ──► data memory
 └──── next PC ◄──────── branch / jump          │                    │
                                               └──── writeback ◄────┘
```

The register file has two combinational read ports and one clocked write port. It exposes 32 architectural registers with 31 stored words and a hardwired zero for `x0`. The synchronous active-high reset clears the stored registers and starts execution at `RESET_PC`, which defaults to zero.

- `imem_addr` is a byte address. Instruction data must settle during the same cycle.
- `dmem_addr` is the effective address rounded down to a word boundary. For a read, supply the containing word combinationally. For a write, latch the enabled bytes on the rising edge. Strobe 0 selects bits 7:0 at `dmem_addr`, strobe 1 selects bits 15:8 at `dmem_addr + 1`, and so on.
- `retire_valid`, `retire_rd`, and `retire_wdata` describe the instruction about to commit. A zero destination indicates no register write. Loads to `x0` still assert `dmem_read`.
- The core implements the RV32I base instructions in a bare-metal execution environment. Memory accesses complete in order, so FENCE completes without further work. ECALL, EBREAK, illegal instructions, and misaligned data accesses or taken control transfers latch `halted` and `trap_cause`. The PC stays at the faulting instruction and no write commits. Reset resumes execution from the reset vector. The ports assume zero-wait-state memory.

See the [RV32I specification](https://docs.riscv.org/reference/isa/unpriv/rv32.html) for instruction semantics.

## FPGA build

Install Yosys, nextpnr-ice40 and IceStorm, then run:

```sh
make synth    # Map the standalone core to iCE40 primitives
make fpga     # Synthesize, place, route and pack the iCEBreaker demo
```

The build targets the iCEBreaker UP5K-SG48 at 12 MHz and writes `build/icebreaker.bin`. Scratch memory occupies address `0x0000` and the result port is at `0x0100`. The demo is designed to light the green LED when it writes 55, and the red LED for an incorrect result or a trap. The pushbutton restarts the core. The LED and reset behavior was verified in simulation.

The routed demo used **1,683 of 5,280 logic cells** and met the 12 MHz target with an estimated **13.90 MHz** maximum clock rate. The [implementation report](docs/implementation.md) records the critical path and separates demo utilization from standalone core synthesis.
