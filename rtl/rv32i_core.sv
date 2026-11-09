module rv32i_core #(
    parameter logic [31:0] RESET_PC = 32'h0
) (
    input  logic        clk,
    input  logic        reset,

    output logic [31:0] imem_addr,
    input  logic [31:0] imem_rdata,

    output logic [31:0] dmem_addr,
    output logic        dmem_read,
    input  logic [31:0] dmem_rdata,
    output logic [31:0] dmem_wdata,
    output logic [3:0]  dmem_wstrb,

    output logic        retire_valid,
    output logic [4:0]  retire_rd,
    output logic [31:0] retire_wdata,
    output logic        halted,
    output logic [3:0]  trap_cause
);
    localparam logic [3:0] INST_MISALIGNED = 4'd0, ILLEGAL = 4'd2,
                           BREAKPOINT = 4'd3, LOAD_MISALIGNED = 4'd4,
                           STORE_MISALIGNED = 4'd6, ECALL = 4'd8;

    logic [31:0] pc, pc_next, pc_plus4, target;
    logic [31:0] regs [1:31];
    logic [31:0] a, b, imm, alu_b, alu_result, writeback, load_data;
    logic [4:0] rs1, rs2, rd;
    logic [6:0] opcode, funct7;
    logic [2:0] funct3;
    logic [1:0] byte_offset;
    logic [3:0] store_mask, fault_cause;
    logic write_rd, load, store, fault, branch_taken, redirect, mem_misaligned;

    assign imem_addr = pc;
    assign pc_plus4 = pc + 32'd4;
    assign opcode = imem_rdata[6:0];
    assign rd     = imem_rdata[11:7];
    assign funct3 = imem_rdata[14:12];
    assign rs1    = imem_rdata[19:15];
    assign rs2    = imem_rdata[24:20];
    assign funct7 = imem_rdata[31:25];
    assign a = rs1 == 0 ? 32'b0 : regs[rs1];
    assign b = rs2 == 0 ? 32'b0 : regs[rs2];

    always_comb begin
        case (opcode)
            7'h23: imm = {{20{imem_rdata[31]}}, imem_rdata[31:25], imem_rdata[11:7]};
            7'h63: imm = {{19{imem_rdata[31]}}, imem_rdata[31], imem_rdata[7],
                          imem_rdata[30:25], imem_rdata[11:8], 1'b0};
            7'h17, 7'h37: imm = {imem_rdata[31:12], 12'b0};
            7'h6f: imm = {{11{imem_rdata[31]}}, imem_rdata[31], imem_rdata[19:12],
                          imem_rdata[20], imem_rdata[30:21], 1'b0};
            default: imm = {{20{imem_rdata[31]}}, imem_rdata[31:20]};
        endcase
    end

    assign alu_b = opcode == 7'h33 ? b : imm;
    always_comb begin
        case (funct3)
            3'b000: alu_result = (opcode == 7'h33 && funct7[5]) ? a - alu_b : a + alu_b;
            3'b001: alu_result = a << alu_b[4:0];
            3'b010: alu_result = {31'b0, $signed(a) < $signed(alu_b)};
            3'b011: alu_result = {31'b0, a < alu_b};
            3'b100: alu_result = a ^ alu_b;
            3'b101: begin
                if (funct7[5])
                    alu_result = $signed(a) >>> alu_b[4:0];
                else
                    alu_result = a >> alu_b[4:0];
            end
            3'b110: alu_result = a | alu_b;
            3'b111: alu_result = a & alu_b;
        endcase
    end

    always_comb begin
        case (funct3)
            3'b000: branch_taken = a == b;
            3'b001: branch_taken = a != b;
            3'b100: branch_taken = $signed(a) < $signed(b);
            3'b101: branch_taken = $signed(a) >= $signed(b);
            3'b110: branch_taken = a < b;
            3'b111: branch_taken = a >= b;
            default: branch_taken = 1'b0;
        endcase
    end

    // The memory bus carries an aligned word address and little-endian byte lanes.
    logic [31:0] effective_addr;
    logic [15:0] shifted_rdata;
    assign effective_addr = a + imm;
    assign dmem_addr = {effective_addr[31:2], 2'b00};
    assign byte_offset = effective_addr[1:0];
    assign shifted_rdata = 16'(dmem_rdata >> {byte_offset, 3'b000});
    assign dmem_wdata = b << {byte_offset, 3'b000};

    always_comb begin
        case (funct3)
            3'b000: load_data = {{24{shifted_rdata[7]}}, shifted_rdata[7:0]};
            3'b001: load_data = {{16{shifted_rdata[15]}}, shifted_rdata[15:0]};
            3'b010: load_data = dmem_rdata;
            3'b100: load_data = {24'b0, shifted_rdata[7:0]};
            3'b101: load_data = {16'b0, shifted_rdata[15:0]};
            default: load_data = 32'b0;
        endcase
        case (funct3[1:0])
            2'b00: store_mask = 4'b0001 << byte_offset;
            2'b01: store_mask = 4'b0011 << byte_offset;
            default: store_mask = 4'b1111;
        endcase
    end

    assign mem_misaligned = (funct3[1:0] == 2'b01 && byte_offset[0]) ||
                            (funct3[1:0] == 2'b10 && byte_offset != 0);
    assign target = opcode == 7'h67 ? (effective_addr & 32'hffff_fffe) : pc + imm;

    always_comb begin
        write_rd = 1'b0;
        load = 1'b0;
        store = 1'b0;
        redirect = 1'b0;
        fault = 1'b0;
        fault_cause = ILLEGAL;
        case (opcode)
            7'h37, 7'h17: write_rd = 1'b1;  // LUI, AUIPC
            7'h6f: begin  // JAL
                write_rd = 1'b1;
                redirect = 1'b1;
            end
            7'h67: begin  // JALR
                write_rd = 1'b1;
                redirect = 1'b1;
                fault = funct3 != 0;
            end
            7'h63: begin
                redirect = branch_taken;
                fault = funct3 == 3'b010 || funct3 == 3'b011;
            end
            7'h03: begin
                write_rd = 1'b1;
                load = 1'b1;
                fault = funct3 == 3'b011 || funct3 >= 3'b110;
            end
            7'h23: begin
                store = 1'b1;
                fault = funct3 > 3'b010;
            end
            7'h13: begin
                write_rd = 1'b1;
                case (funct3)
                    3'b001: fault = funct7 != 7'h00;
                    3'b101: fault = funct7 != 7'h00 && funct7 != 7'h20;
                    default: fault = 1'b0;
                endcase
            end
            7'h33: begin
                write_rd = 1'b1;
                fault = funct7 != 7'h00 &&
                        !(funct7 == 7'h20 && (funct3 == 3'b000 || funct3 == 3'b101));
            end
            7'h0f: fault = funct3 != 0;  // FENCE: all accesses already complete in order.
            7'h73: begin
                fault = 1'b1;
                case (imem_rdata)
                    32'h0000_0073: fault_cause = ECALL;
                    32'h0010_0073: fault_cause = BREAKPOINT;
                    default: fault_cause = ILLEGAL;
                endcase
            end
            default: fault = 1'b1;
        endcase

        if (pc[1:0] != 0) begin
            fault = 1'b1;
            fault_cause = INST_MISALIGNED;
        end else if (!fault) begin
            if (redirect && target[1:0] != 0) begin
                fault = 1'b1;
                fault_cause = INST_MISALIGNED;
            end else if ((load || store) && mem_misaligned) begin
                fault = 1'b1;
                fault_cause = store ? STORE_MISALIGNED : LOAD_MISALIGNED;
            end
        end
    end

    always_comb begin
        case (opcode)
            7'h37: writeback = imm;
            7'h17: writeback = target;
            7'h67, 7'h6f: writeback = pc_plus4;
            7'h03: writeback = load_data;
            default: writeback = alu_result;
        endcase
    end

    assign pc_next = redirect ? target : pc_plus4;
    assign retire_valid = !reset && !halted && !fault;
    assign retire_rd = retire_valid && write_rd ? rd : 5'b0;
    assign retire_wdata = retire_rd == 0 ? 32'b0 : writeback;
    assign dmem_read = retire_valid && load;
    assign dmem_wstrb = retire_valid && store ? store_mask : 4'b0;

    always_ff @(posedge clk) begin
        if (reset) begin
            pc <= RESET_PC;
            halted <= 1'b0;
            trap_cause <= 4'b0;
            for (int i = 1; i < 32; i++)
                regs[i] <= 32'b0;
        end else if (!halted) begin
            if (fault) begin
                halted <= 1'b1;
                trap_cause <= fault_cause;
            end else begin
                pc <= pc_next;
                if (retire_rd != 0)
                    regs[retire_rd] <= writeback;
            end
        end
    end
endmodule
