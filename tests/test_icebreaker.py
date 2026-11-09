import cocotb
from cocotb.triggers import Timer


async def tick(dut, count):
    for _ in range(count):
        dut.clk_12m.value = 0
        await Timer(5, unit="ns")
        dut.clk_12m.value = 1
        await Timer(5, unit="ns")


@cocotb.test()
async def demo_reports_sum_and_restarts(dut):
    dut.button_n.value = 1
    await tick(dut, 2)
    assert int(dut.led_green_n.value) == 1
    assert int(dut.led_red_n.value) == 1

    await tick(dut, 45)
    assert int(dut.led_green_n.value) == 0
    assert int(dut.led_red_n.value) == 1

    dut.button_n.value = 0
    await tick(dut, 4)
    assert int(dut.led_green_n.value) == 1
    assert int(dut.led_red_n.value) == 1

    dut.button_n.value = 1
    await tick(dut, 45)
    assert int(dut.led_green_n.value) == 0
    assert int(dut.led_red_n.value) == 1
