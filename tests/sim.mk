SIM := verilator
TOPLEVEL_LANG := verilog
COCOTB_TOPLEVEL := $(SIM_TARGET)
COCOTB_TEST_MODULES := test_$(SIM_TARGET)
SIM_BUILD := build/sim/$(SIM_TARGET)
COCOTB_RESULTS_FILE := $(SIM_BUILD)/results.xml
VERILOG_SOURCES := $(CURDIR)/rtl/rv32i_core.sv
export PYTHONPATH := $(CURDIR)/programs:$(CURDIR)/tests:$(PYTHONPATH)

ifeq ($(SIM_TARGET),icebreaker)
VERILOG_SOURCES += $(CURDIR)/fpga/icebreaker.sv
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
