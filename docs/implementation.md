# iCE40 implementation

The iCEBreaker demo was synthesized with Yosys 0.69+post (143eb14f9), placed and routed with nextpnr-ice40 0.11.1 (Homebrew revision 1), and packed with IceStorm 1.1 on macOS arm64. The target is UP5K-SG48 with a 12 MHz clock constraint and placement seed 1. Pin assignments follow the [IceStorm iCEBreaker example](https://github.com/YosysHQ/icestorm/blob/main/examples/icebreaker/icebreaker.pcf).

| Post-route resource | Used | Available |
| --- | ---: | ---: |
| Logic cells | 1,683 | 5,280 |
| Block RAMs | 0 | 30 |
| I/O cells | 4 | 39 |
| Global buffers | 2 | 8 |

The longest same-clock path was **71.92 ns**, leaving **11.41 ns** against the 83.33 ns period. The path starts at `pc[19]` and ends at the clock enable of a bit in `cpu.regs[30]`. It passes through the ROM address check and the decode/datapath logic that qualifies register writeback. The endpoint is a write enable because the same cycle must resolve instruction decode and fault checks before it can commit a register update. nextpnr attributes 20.90 ns to logic and 51.02 ns to routing, so routing accounts for about 71% of the path delay. The estimated maximum clock rate is 13.90 MHz for this routed demo.

The ROM only supplies the demo instructions, so the FPGA build can prune parts of the core. Standalone synthesis with unconstrained instruction and data inputs mapped the core to 3,167 LUT4s, 1,036 flip-flops and 185 carry cells. The board design mapped to 1,283 LUT4s, 439 flip-flops and 140 carry cells before packing. LUT counts and packed logic-cell counts describe different stages of the flow.

| Command | Reports |
| --- | --- |
| `make synth` | `build/core-yosys.log` |
| `make fpga` | `build/yosys.log`, `build/nextpnr.log`, `build/timing.json` |

The clock rate is a place-and-route estimate. The bitstream and pin constraints were generated for the iCEBreaker, and the demo was exercised in RTL simulation. Physical board validation is pending.
