module icebreaker (
    input  logic clk_12m,
    input  logic button_n,
    output logic led_green_n,
    output logic led_red_n
);
    // Start in reset after configuration and synchronize the pushbutton.
    logic [1:0] reset_pipe;
    initial reset_pipe = 2'b11;
    always_ff @(posedge clk_12m)
        reset_pipe <= {reset_pipe[0], !button_n};

    logic reset, halted, passed, failed;
    logic [31:0] pc, instruction, addr, rdata, wdata;
    logic [3:0] wstrb;
    logic [31:0] rom [0:15];
    logic [31:0] scratch;
    initial $readmemh("build/demo.hex", rom);

    assign reset = reset_pipe[1];
    assign instruction = pc[31:6] == 0 && pc[1:0] == 0 ? rom[pc[5:2]] : 32'b0;
    assign rdata = addr == 0 ? scratch : 32'b0;
    assign led_green_n = !passed;
    assign led_red_n = !(failed || halted);

    always_ff @(posedge clk_12m) begin
        if (reset) begin
            scratch <= 32'b0;
            passed <= 1'b0;
            failed <= 1'b0;
        end else begin
            if (addr == 0)
                for (int lane = 0; lane < 4; lane++)
                    if (wstrb[lane])
                        scratch[8*lane +: 8] <= wdata[8*lane +: 8];

            if (addr == 32'h100 && |wstrb) begin
                passed <= wstrb == 4'b1111 && wdata == 32'd55;
                failed <= wstrb != 4'b1111 || wdata != 32'd55;
            end
        end
    end

    rv32i_core cpu (
        .clk(clk_12m), .reset(reset),
        .imem_addr(pc), .imem_rdata(instruction),
        .dmem_addr(addr), .dmem_read(), .dmem_rdata(rdata),
        .dmem_wdata(wdata), .dmem_wstrb(wstrb),
        .retire_valid(), .retire_rd(), .retire_wdata(),
        .halted(halted), .trap_cause()
    );
endmodule
