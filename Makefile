PYTHON ?= python3

.DELETE_ON_ERROR:
.PHONY: test lint synth fpga clean

test: build/demo.hex
	$(MAKE) -f tests/sim.mk SIM_TARGET=rv32i_core
	$(MAKE) -f tests/sim.mk SIM_TARGET=icebreaker

lint:
	verilator --lint-only -Wall --top-module rv32i_core rtl/rv32i_core.sv
	verilator --lint-only -Wall -Wno-PINCONNECTEMPTY --top-module icebreaker rtl/rv32i_core.sv fpga/icebreaker.sv

fpga: build/icebreaker.bin
synth: build/rv32i_core.json

build/demo.hex: programs/demo.py programs/rv32i.py
	mkdir -p build
	$(PYTHON) programs/demo.py $@

build/rv32i_core.json: rtl/rv32i_core.sv
	mkdir -p build
	yosys -Q -q -l build/core-yosys.log -p 'read_verilog -sv $<; synth_ice40 -top rv32i_core -json $@; stat'

build/icebreaker.json: rtl/rv32i_core.sv fpga/icebreaker.sv build/demo.hex
	yosys -Q -q -l build/yosys.log -p 'read_verilog -sv rtl/rv32i_core.sv fpga/icebreaker.sv; synth_ice40 -top icebreaker -json $@; stat'

build/icebreaker.asc: build/icebreaker.json fpga/icebreaker.pcf
	nextpnr-ice40 --up5k --package sg48 --pcf fpga/icebreaker.pcf \
		--json $< --asc $@ --freq 12 --seed 1 --log build/nextpnr.log \
		--report build/timing.json --detailed-timing-report

build/icebreaker.bin: build/icebreaker.asc
	icepack $< $@

clean:
	rm -rf build
