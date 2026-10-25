# 交接文档：ISP RTL 仿真验证工作

## ✅ 2026-10-02（第七轮）：point-ops 周期精确验证收口（旧 WIP 关闭）+ 全量回归基线复核

本轮**未改动任何 RTL**，纯验证层收口 + 文档订正。上一轮遗留的唯一 WIP（point-ops 四模块
周期精确比对卡在采样相位对齐）已通过 2026-08-03 推荐的"路线 1（cocotb）"解决，README 中
的⚠️ WIP 标注属过期信息，本次已订正。

### 1. 结论：point-ops 四模块已全绿

`sim/run_pointops_cocotb.py` → `test_pointops.py`（cocotb 2.0.1 + icarus）实测通过：

```
PART 1: cycle-accurate replica vs RTL (43848 cycles)
  [LOG      ] max_diff=0 over 43848 cycles
  [EMBOSS   ] max_diff=0 over 43848 cycles
  [HISTOGRAM] max_diff=0 over 43848 cycles
  [EQ       ] max_diff=0 over 43848 cycles
PART 2: LOG/EMBOSS/HISTOGRAM/HIST_EQ 四项功能意图核对全部 OK
Overall: PASS (cycle-accurate replica OK, 1 functional findings)
```

该流程**已接入 `run_all.py` 第 11 条 flow**（`run_pointops_cocotb`，见 run_all.py:170），
随主回归一起跑。八个向量（vid1~8，LCG 种子 0x12345678，RGB565 打包）+ 320 拍帧间隔的
激励设计见 2026-08-03 章节，此处未改动。

### 2. 相位对齐问题的收口方式（回答 8/03 §4 的路线选择）

采纳**路线 1（cocotb 驱动）**。关键做法：`RisingEdge` 后读 post-edge 输出、写 pre-edge 输入，
相位天然对齐，彻底绕开 Verilog task 里`posedge+#1` / `negedge` 打印引入的一拍偏移。
旧的三次迭代（8/03 §3 踩坑表 1/2/3）结论保留——**驱动时机不是根因，根因是把"活动周期
计数"和"dump 行"两套时间基混在一起**；cocotb 让两者共用同一个边沿计数后自然消失。

### 3. 两条 RTL finding 的定性（8/03 §5 遗留，**已可下结论**）

| 编号 | 现象 | 定性 |
|---|---|---|
| F1 | `HISTOGRAM_EQ` 缩放 `(v<<5+v<<4)+(v<<2+v<<1)` = **×54** 而非 640×480 帧期望的 ≈255/307200 | **不是 bug，是硬编码的帧尺寸假设**。×54>>16 只在 640×480 帧下成立；PART 2 用真实 CDF 核对时确认 "ram2 == CDL scaled by the RTL's hardcoded x54>>16"。若要支持其它帧高需改 RTL（本轮未做，见 §6） |
| F2 | 1 次读取为 X/Z 被跳过（`histogram_eq_value` 在 flush 前未建立） | **非缺陷**，是 flush 前的未初始化窗口，模型与 RTL 同样为 X；跳过即可，无需处理 |

因此 8/03 §5 列出的 `wea1` 游程归一 / BLANK 上升沿误写一拍 / 两个 always 块组合反馈交叉
等"疑似 RTL 问题"，在周期精确比对归零后**均未表现为与意图的偏差**，PART 1 已把"as-written
RTL"钉死，PART 2 确认功能意图一致，故本轮不动 RTL。若将来改 F1，需同步更新 `verify_pointops.py`
里的 `HistEqModel`（它复刻了 ×54>>16）。

### 4. `run_iverilog_all.py` 未新增 point-ops 测试（刻意）

8/03 §6 提到 PART 1 全绿后要"接入 run_iverilog_all.py（新增测试 5）"。本轮**判定不接**：
该脚本定位是"纯 iverilog 冒烟、不依赖 cocotb"，而 point-ops 的绿来自 cocotb 路径；为接它
而改用已被取代的 Verilog 测试台（`tb_pointops.v` + `run_pointops.py`，PART 1 已知 FAIL）
等于把失败流程拉进回归。`run_all.py` 第 11 条 flow 已提供同等覆盖。

### 5. 顺带修复：`run_iverilog_all.py` 计时显示 bug

ISP_TOP 全系统测试实际仿真 30ms，但摘要恒显`PASS (0.0s)`——`test_isp_top()` 在成功分支
`return True, 0.0, ""`（run_iverilog_all.py:140）把 `run_sim` 返回的 `elapsed` 丢弃了。
本轮已改为透传 `elapsed`，避免"显示 0 秒"被误读成没跑。

### 6. 本轮回归基线（改动文档/脚本后复跑）

| 命令 | 结果 |
|---|---|
| `python sim/run_all.py` | **12/12 ALL PASS** |
| `python sim/run_iverilog_all.py` | **4/4 ALL PASS**（test 4 实测耗时 ~10 分钟，`grey_out_3.txt` 非零 → SDRAM 通路 alive） |

### 7. 遗留事项（本轮未做，按优先级）

- [ ] **F1 是否改 RTL**：让 `HISTOGRAM_EQ` 缩放跟随实际帧高，而非硬编码 ×54>>16。改动会
      波及 `verify_pointops.py` 的 `HistEqModel` 参照，需一并更新。**动手前先问用户。**
- [ ] **`sim/` 产物体积**：`isp_top_tb.vcd` 约 2.87GB，占 `sim/` 绝大部分。根因是
      `ISP_testbench/ISP_TOP_tb.v:52-53` 做了 `$dumpvars(0, ISP_TOP_tb)` 全层次转储且跑满
      30ms。可改为门控（`$dumpoff`/`$dumpon` 按行）或只 dump 顶层若干信号，回归价值不变。
- [ ] **版本控制**：仓库至今**不是 git 仓库**。2026-09-19 的 404 覆盖 9 个测试台却无历史可
      回滚，属实操教训。建议 `git init` + `.gitignore` 忽略 `*.vcd` / `*.vvp` / `*_dump.txt` /
      `sim/output/` / `sim/build_*/`。（本轮按用户要求跳过。）
- [ ] `run_pointops.py` / `tb_pointops.v` / `verify_pointops.py` 可考虑删除或加显著废弃标注
      （README 已加注"请勿接入回归"，代码内未加）。

---

## ✅ 2026-09-19（第六轮）：9 个仿真测试台被 404 覆盖，重建后 12/12 + 全系统回归全绿

接手优先看这里。2026-08-23 18:52 有 9 个 `sim/tb_*.v` 被一次性覆盖成 `404: Not Found`
（疑似某次从网上拉文件时把 404 body 直接写进文件），`run_all.py` 从 12/12 ALL PASS
掉到 4/12。**RTL 一行未动**，9+1 个测试台已按各 `run_*/test_*/verify_*` 脚本的接口
需求重建，`run_all.py` 回到 **12/12 ALL PASS**，`run_iverilog_all.py` 1~4（含慢速
ISP_TOP 全系统，`grey_out_3.txt` 非零）也全过。

### 被覆盖的文件（均为 14 字节，重建前）

`tb_top.v` / `tb_filters.v` / `tb_filters_standalone.v` / `tb_canny_thresh.v` /
`tb_sobel_thresh.v` / `tb_waveform.v` / `tb_histogram.v` / `tb_rgb_uv_dump.v` /
`tb_pointopts_cocotb.v`（注意这个文件名本身就是错的，多了个 `s`，没有脚本引用它，
已删除；正确文件名是新建的 `tb_pointops_cocotb.v`）。

### 重建要点（下次再丢，按这个恢复）

| 文件 | 关键约束（丢了就过不了） |
|---|---|
| `tb_top.v` | cocotb 包裹层，实例必须叫 `uut`（`test_rgb2yuv.py` 全经 `dut.uut` 访问） |
| `tb_filters.v` | 高斯实例必须叫 `u_gaussian`（`test_probe.py` 要钻进 `U_MATRIX_GENERATOR_0.o_matrix*` 和 `gs_1/2/3/sum/data`）；顶层端口 `g_/s_/m_{BLANK,HSYNC,VSYNC,display}` + `thresh_min/max` |
| `tb_pointops_cocotb.v` | 实例名 `u_log/u_emboss/u_hist/u_eq` 是 load-bearing（含 `u_eq.u_ram_1/2.mem`）；EMBOSS 的 `shreshold` 接 `8'd150` |
| `tb_waveform.v` | 信号声明顺序必须复刻原 VCD 的 identifier 分配（`verify_vcd.py` 按 `*`/`"` 硬找输入输出）；10 步颜色序列 Black→Red→Green→Blue→White→Red→Green→Blue→White→Black，每步 40ns |
| `tb_rgb_uv_dump.v` | 模块名必须叫 `tb_rgb2yuv_dump`（带 y），文件名是 `tb_rgb_uv_dump.v`；dump `U0/V0` 要用层次引用 `uut.U0/uut.V0`（不是端口）；每输入保持 5 拍 |
| `tb_sobel_thresh.v` / `tb_canny_thresh.v` | 向量从 `verify_thresh_path.py` 的 `SOBEL_VECTORS/CANNY_VECTORS` 逐字转抄；时序必须是"negedge 驱动→posedge 采样→negedge dump，一拍一记录"，多等一个沿就会出现 col 翻倍漂移；`d_*` 标志用 posedge 捕获 |
| `tb_filters_standalone.v` | 自检，输出 `>>> PASS`；采样必须在帧内（rows 5..7），drain 后采样窗口只剩一行有效数据（`gs=32` 陷阱） |

### 验证结果

- `run_all.py` 12/12 ALL PASS；thresh 路径 `verify_thresh_path.py` 意图模型 0 误差，
  反向证明 canny `2'b01` 分支修复仍在生效。
- `run_iverilog_all.py` 1/2/3/4 全过。
- 调试用临时文件（`tb_dbg.v`、`*_check.vvp`）已删；中间产物 dump/VCD 已就地重生。

### 遗留（和以前一样）

- 本仓库仍不是 git 仓库。本轮已在项目根目录外打了 `image-processing-backup-2026-09-19.zip`
  快照，若根目录找不到就问用户要。
- `HIST_EQ ×54>>16` 640×480 尺度假设、`run_pointops.py` 旧 dump 版待删，均未动。

---

## ✅ 2026-08-13（第五轮·续2）：新发现并修复 RTL bug——matrix_generator 的 col_cnt 清零依赖 HSYNC 高电平，与 VGA 低有效时序冲突；端到端 isp_out 非零验证通过

接手优先看这里。在验证"isp_out 全 0 是否仅因渐变图无边缘"时,用 `sim/gen_edge_image.py` 生成棋盘边缘图重跑 ISP_TOP_tb,发现 **isp_out 依然全 0**,深挖出又一个真实 RTL bug(之前所有验证都被自定义高有效 HSYNC 测试协议掩盖)。

### 根因

`image_processing/Matrix_generator/matrix_generator.v` 的 col_cnt 清零条件:

```verilog
else if(i_HSYNC || i_VSYNC) begin
  col_cnt <= 10'b0;
end
```

假设 HSYNC/VSYNC 是**高有效脉冲**(test_golden 等自定义协议:1 拍高脉冲)。但 ISP_TOP 的真实时序源是 `VGA_CTRL.v`,其 H_SYNC/V_SYNC 是**低有效**(每行 800 拍中 704 拍为 1、96 拍为 0;每帧 525 行中 523 行为 1)。因此 `i_HSYNC || i_VSYNC` 在绝大多数周期为 1 → **col_cnt 恒被清零 → 矩阵窗口永不建立 → gx/gy/sqrg 恒 0 → sobel 无输出 → canny is_edge 恒 0**。

之前 verify_golden/verify_thresh_path/test_isp_chain 全部通过,是因为测试台用"1 拍高有效脉冲"驱动 i_HSYNC,恰好在脉冲拍清零、其余时间不复位——掩盖了此 bug。这是典型的"测试协议与真实时序不一致"陷阱。

### 修复

改用 HSYNC/VSYNC **下降沿**清零 col_cnt(下降沿 = 行/帧边界,两种协议下都正确):

```verilog
reg r_HSYNC_d, r_VSYNC_d;
always @(posedge clk) begin r_HSYNC_d <= i_HSYNC; r_VSYNC_d <= i_VSYNC; end
wire hsync_fall = r_HSYNC_d & ~i_HSYNC;
wire vsync_fall = r_VSYNC_d & ~i_VSYNC;
...
else if(hsync_fall || vsync_fall) col_cnt <= 10'b0;
```

同步更新 `sim/verify_golden.py` 的 MatrixGenerator 模型(同样用下降沿),保持周期精确比对成立。

### 验证结果

- 边缘图(棋盘+灰条纹)下 ISP_TOP_tb:sobel sqrg=703>120、canny is_edge=1 **首次出现**
- `isp_out_3/4/5.txt` 出现非零输出(边缘检测结果),`grey_out_3..5` 非零(RGB2YUV 灰度)
- **前 2 帧输出全 0 是乒乓读空区的正常行为**(读侧初始在 bank2,写侧写完 bank0 切换后读侧才切回)
- `run_all.py` 12/12 ALL PASS(verify_golden 模型已同步,周期精确仍成立)

### 新文件

- `sim/gen_edge_image.py`:生成棋盘+条纹边缘测试图(替代渐变图验证边缘检测),`--restore` 可还原渐变图(备份在 `test_image.gradient.hex`)

### 数据正确性最终确认(2026-08-13 晚)

对"读回数据是否真的正确"做了三层核对,全部通过:

1. **写侧**:`tb_wrcheck` 在写完第一帧后 dump SDRAM Bank0[0..19] 与 `test_image` 逐字比对——**完全一致**。
2. **读侧**:`tb_rdseq` 在乒乓切换后(读侧回到 bank0)按 `rd_ack` 采样 `rdata`(与 `sdram_rd_addr` 同拍),87419 次检查 **0 错误**——读回序列与 test_image 逐像素一致。
3. **早前疑问澄清**:
   - "grey_out_5 只有 54 个唯一值"——**正常**:RGB2YUV 的 `display_data = {Y0[7:3], Y0[7:2], Y0[7:3]}`,Y 只有 8 位,6 位有效打包后最多 64 个唯一值,渐变图 54 个合理。
   - "早前 0/715 数值不匹配"——**核对脚本方法错误**:误用 `r_data_out`(rd_fifo 异步输出)对 `sdram_rd_addr`(读请求地址),两者不同拍。正确做法:用 `rd_ack`/`rdata`(SDRAM 直接输出)或 `data_req` 消费时刻采样。
   - "isp_out 全 0"——渐变图无边缘,canny 二值输出全 0 属预期;边缘图下 isp_out_3/4/5 非零已验证。

**结论:SDRAM 数据通路(写→存→读→显示)逐像素正确,ISP_TOP 全系统验证闭合。**

### 遗留

- SDRAM 链路的周期精确 Python 模型(verify_golden 式逐周期比对) **已完成**(2026-08-13晚):`verify_sdram_loop.py` 逐周 期复刻 sram_ctrl + fifo_ctrl + FWFT fifo + 简化 SDRAM 响应,与 RTL (tb_sdram_loop_dump.v) 比对,22703 拍 0 差错(尾部边界差 2 拍属 200ns 撤销时序差异)。 
- 建议:若后续需微调 SDRAM 控制器时序,先跑 `verify_sdram_loop.py` 检查周期精确不破坏。
- `ISP_TOP_tb.v` 仿真时长 30ms(乒乓切换在 23.5ms,够首帧读回);若要多帧可再加长。
- `run_iverilog_all.py` 的 ISP_TOP 冒烟已断言 `grey_out_3..5` 非零(渐变图),可考虑边缘图时断言 isp_out 非零。

---

承接上文的 sram_ctrl/行为模型修复。本轮把 ISP_TOP 全系统(含 SDRAM 乒乓)跑出真实数据:`grey_out_5.txt` 54 个唯一值、`r_data_out` 逐像素变化、RGB2YUV Y0 输出 35~90 与图像内容一致。**注意:前 4 帧输出全 0 是乒乓读空区的正常行为,不是 bug。**

### 最后一层根因:ISP_TOP_tb.v 复位协议

`wr_fifo`/`rd_fifo` 的复位依赖 `rst`(posedge 采样)。原 tb 复位是 `rst_n=1; #40 rst_n=0; #20 rst_n=1`——低电平仅 20ns,而 clk_wr 周期 40ns,**低电平窗口内没有任何 wr_clk posedge**,fifo 的 `wr_ptr` 从未被复位(保持 x)→ 写路径全死(SDRAM 从未写入)→ 全 0。这是**测试台 bug,不是 RTL bug**。修复:

```verilog
rst_n = 0;
#120 rst_n = 1;   // 低电平必须覆盖至少一个 wr_clk posedge(40ns 周期)
```

### 乒乓模式的正常行为(勿误判为 bug)

- 读侧复位地址 = `{~rd_min[23], ...}` = 0x800000(bank2),写侧从 0(bank0)开始。
- 第一帧:写 bank0,读 bank2(空)→ 输出全 0(正常,第一帧没有上一帧可显示)。
- 写侧 12.3ms 写完 bank0 后乒乓切到 bank2;读侧读完空 bank2(约 23.5ms 触发切换)后切到 bank0 → **从第 5 个 VSYNC 帧开始输出真实数据**(`grey_out_5.txt`)。
- 因此核对输出内容必须看乒乓切换后的文件(如 `grey_out_5.txt`),`grey_out_1..4` 全 0 属预期。

### isp_out 全 0 也属预期(非 bug)

ISP_TOP 默认宏 `sobel_en + canny_en`:display 是 canny 二值输出(is_edge ? 0xFFFF : 0)。test_image 是平滑渐变,边缘像素稀疏,故 isp_out 几乎全 0。要看非 0 的最终 display,需用含明显边缘的测试图(后续可做)。

### 验证证据

- `tb_sdram_loop.v`(独立回环):64/512 字写→读全对(0 mismatches)
- ping_pong_en=0 探针:r_data_out 非零 146 万次、Y0 逐像素变化、display 与 Y0 打包一致
- ping_pong_en=1 全系统:乒乓 23.5ms 切换(`RD 8695296 -> 0`)、grey_out_5 有真实数据
- `run_iverilog_all.py` 4/4 PASS、`run_all.py` 12/12 PASS

### 文件改动

| 文件 | 改动 |
|---|---|
| `ISP_testbench/ISP_TOP_tb.v` | 复位改为低 120ns(覆盖 wr_clk posedge);仿真时长 4ms → 40ms(写满一帧 12.3ms + 乒乓切换) |

---

接手优先看这里。长期挂起的"ISP_TOP 输出全 0"(`output/isp_out_1.txt`/`grey_out_1.txt` 全部 0000)根因定位并修复。这是 **RTL 真实 bug**(非验证层问题),修复后独立回环 64/512 字全部逐字正确,全量回归 12/12 全绿。

### 根因链(三层)

1. **行为模型 `wr_fifo`/`rd_fifo` 的 count 语义错误**(`sim/ip/sdram_ip_wrappers.v`):
   FWFT FIFO 中预取进 `dout_reg` 的字仍可读,真实占用 = `(wr_ptr - rd_ptr) + dout_valid`,但原实现 `count_w/count_r = wr_ptr - rd_ptr` 少算 1。导致 `fifo_ctrl` 的 `wr_data_count >= br_length` 写请求阈值差 1 → **写侧死锁**(wr_fifo 积压 511 字,512 阈值永不触发)→ SDRAM 从未被写入 → 读回全 0。已修(`count_w` 和 `count_r` 都加 `dout_valid`)。

2. **`sram_ctrl.v`(即 sdram_ctrl,文件名为 sram_ctrl.v)写时序错位**:
   - `wr_ack` 原在 `WR_PRE && wr_req` 就拉高(WRITE 命令前 1 拍),而 `wr_ack` 同时是 wr_fifo 的 `rd_en` → FWFT 提前弹出首字,写突发数据错位成 `0,2,2,4,4,6,6...`(奇数丢失、偶数重复)。改为从 `WRITE` 状态才拉高。
   - `wr_en` 原由 `wr_ack` 寄存派生(晚 2 拍),DQ 在 WRITE 命令拍还是高阻,SDRAM 首拍采到 zzzz。改为由 state 直接驱动(`WR_PRE|WRITE|WD && cnt<br_length-1`),DQ 提前一拍就绪。
3. **`sram_ctrl.v` 读时序 rd_ack 窗口过宽**:原 `rd_ack` 从 `state==RD && state_cnt>=3` 一路拉到 `rd_post_d`(≈2×br_length 拍),rd_fifo 每个突发多收约 1 个突发长度的垃圾字 → 读流每突发漂移 1 字(表现为 rd[48..] 读到 0x2f 而非 0x30)。改为独立 `rd_data_cnt` 计数器(READ 状态清零)+ 精确 `br_length` 拍窗口 + `rd_post_d` 保持到窗口尾,读侧逐字对齐。

### 验证结果

- `sim/tb_sdram_loop.v`:独立回环测试台(sdram_top + sdram_model),64 字、512 字写→读回全对(0 mismatches)
- `run_iverilog_all.py`:4/4 PASS(含 ISP_TOP 全系统冒烟)
- `run_all.py`:12/12 ALL PASS

### 关键经验

- **测试台驱动时序会掩盖/制造假 bug**:最初看到写侧 `0,2,2,4` 错位,一度以为是测试台在 posedge 后设置 `w_data_in` 的调度竞争;改为 negedge 驱动后写入正确、错位消失——但 A/B 对照(恢复原始 sram_ctrl + 修复 count)证明 **sram_ctrl 原始写时序确实有 bug**(原始版 rd[0] 读到 0001 而非 0000)。两件事独立,都要修。
- **回环测试不要用 posedge 后设置输入**:用 `@(negedge clk)` 驱动,让信号在采样沿前稳定,避免 iverilog delta 竞争。
- **rd_fifo 读侧要等 `dout_valid` 再拉 rd_en**(空 fifo 时 r_data_out 保持旧值,会造成假错位)。

### 文件清单

| 文件 | 改动 |
|---|---|
| `sim/ip/sdram_ip_wrappers.v` | `wr_fifo` 的 `count_w`/`count_r` 加 `dout_valid`(FWFT 占用计数修正) |
| `sdram_controller/sram_ctrl.v` | 写:wr_ack 从 WRITE 状态拉高、wr_en 由 state 驱动;读:rd_data_cnt 计数器 + rd_ack 精确 br_length 窗口 |
| `sim/tb_sdram_loop.v` | 新增:独立 SDRAM 写→读回环测试台(negedge 驱动,读侧等 dout_valid) |
| `docs/HANDOFF.md` | 本轮记录 |

### 遗留

- `ISP_TOP_tb.v` 输出文件仍是全 0?—— 不,修复后 `isp_out_1.txt`/`grey_out_1.txt` 应非全 0;但 tb 只跑 4ms,一帧 640×480 数据写入需 12.3ms,仿真时长不足以写完一帧,建议后续把 `#4000000` 加长(如 20ms)再核对输出内容。
- SDRAM 链路的周期精确 Python 模型(如 verify_golden 那样逐周期比对)仍未建,回环测试目前是数值级验证。

---

接手优先看这里。补上了 README/HANDOFF 长期挂起的目标——**ISP_TOP 全链路端到端周期精确验证**（RGB565 → RGB2YUV → LOG → 高斯/中值 → Sobel → Canny，绕过 SDRAM 回放）。新建 `sim/tb_isp_chain.v` + `sim/verify_isp_chain.py` + `sim/test_isp_chain.py` + `sim/run_isp_chain.py`，已注册为 `run_all.py` **第 12 条流程**，当前 **12/12 ALL PASS**。

### 验证结果

```
ISP chain: 33249 cycles (5 帧 RGB565 测试图), 0 mismatches
链条: RGB2YUV.Y0/disp/同步 → LOG.disp → gauss.disp → median.disp →
      sobel.disp/canny_in → canny.disp, 全部逐周期 max_diff=0
```

### 拓扑说明（重要）

ISP_TOP 是**并联**结构：RGB2YUV 的 Y0 同时喂给 LOG/HISTOGRAM/各滤波器，sobel→canny 是唯一串联。测试台按此布局（HISTOGRAM/HISTOGRAM_EQ 因协议冲突不在此链，已有 test_pointops 覆盖）。

### 本轮发现并修复的验证器 bug（均在验证层，RTL 未动）

| 文件 | Bug | 影响 |
|---|---|---|
| `sim/verify_golden.py` | ① Gaussian/Median/Sobel 的 `r_hsync/r_vsync/r_blank` 移位方向反了（新值放 MSB，RTL 是放 bit0）且同步输出在**移位后**读；② Sobel phase tie-break 误用**新** direction（RTL 读旧 direction）；③ Sobel phase 复位值应为 1（RTL 无复位分支，gx=gy=0/dir=0 推导出 01）；④ canny_in 的 phase 字段误用本拍 nphase（RTL 用寄存器旧 phase） | 这些模型只验过 display_data，同步/canny_in 从未比对，故此前未暴露；ISP 链比对同步+canny_in 后全部修正 |
| `sim/verify_isp_chain.py` | CannyStage/CannyModel 返回的是"本拍新值"（对齐 negedge dump），链测试用 posedge 前读协议，需呈递**旧值**（is_edge 用更新前） | canny.disp 差 1 拍 |

### 文件清单

| 文件 | 说明 |
|---|---|
| `sim/tb_isp_chain.v` | 直通链路测试台：RGB2YUV + LOG + gaussian + median + sobel + canny（不含 SDRAM/HISTOGRAM） |
| `sim/verify_isp_chain.py` | 链式周期精确模型：复用 verify_pointops(LOG)/verify_golden(矩阵+滤波)/verify_thresh_path(Canny) 单模块模型按 ISP_TOP 连线串联 |
| `sim/test_isp_chain.py` | cocotb 驱动：复位 → 帧首 VSYNC(1拍 BLANK=1) → 640×10 像素(HSYNC 合并行尾) → 40 拍 gap → 8 拍复位(gap 后) → drain；逐周期比对全部中间信号 |
| `sim/run_isp_chain.py` | 一键入口：编译（含 behavioral FIFO/CORDIC/blk_mem IP 模型）+ cocotb 运行 |
| `sim/run_all.py` | 注册第 12 条流程，当前 12/12 ALL PASS |

### 遗留（非本次范围）

- SDRAM 回放链路（sdram_top/fifo_ctrl/sram_ctrl 周期精确模型）仍未建——工作量大，且 SDRAM 时序非验证重点，留二期。
- ISP_TOP 全宏组合冒烟（含 SDRAM）仍由 `run_iverilog_all.py` #4 覆盖（能跑通、无 golden 对照）。

---

接手优先看这里。8-03 交接的 PART 2 遗留两处功能偏差已全部结案：**RTL 一行未改**，根因是 `sim/test_pointops.py` 的驱动协议（每帧复位 + VSYNC 脉冲后立即出像素、无帧消隐期）与真实 VGA 时序不一致；修正协议并同步修正验证器后，四模块 PART 1 周期精确 43848 cycles max_diff=0，PART 2 三个功能检查（LOG/EMBOSS/HISTOGRAM 伪拉伸/HIST_EQ ram2）全部 OK。

### 结论（对 8-03 §PART 2 两条偏差的最终判定）

1. **HISTOGRAM 拉伸退化为恒等 —— 协议问题，非 RTL bug**。
   - 原测试协议：每帧 `reset_dut_and_models()`（复位 8 拍）→ VSYNC 脉冲 1 拍 → **立即** 8×640 像素 → 320 拍 gap。VSYNC 下降沿（`i_VSYNC_neg`）在第 2 像素拍触发，此时 `min/max` 只统计了首像素（单像素 A=B），`min_r/max_r` 锁存的是当前帧第一像素 → num=y、den=1 恒等映射。
   - 真实 VGA（`VGA_CTRL.v`）：VSYNC 在帧首（v_cnt 0..1），但其后还有 **33 行帧消隐**（v_cnt 2..34）才开始像素。VSYNC 下降沿落在消隐期：`min/max` 保持上一帧完整统计 → `min_r/max_r` 锁存上一帧 A/B → 当前帧用它拉伸。**这才是"伪拉伸"的意图**。
2. **HISTOGRAM_EQ ram2 映射全错 —— 同样协议问题，非 RTL bug**。
   - 原协议下 `histogram_value_valid` 扫描窗口（VSYNC 下降沿后 2~257 拍）恰好覆盖帧首 ~255 个像素：扫 ram1 清零与像素累积相互污染，hv 累加被像素读携带 → ram2 全 0/饱和。
   - 真实时序下扫描窗口全部落在帧消隐期（BLANK=0），addrb1=r_addr 扫描、wea1 清零、hv 累加 CDF 全部正确；ram2 写入地址（`r_addr_delay[39:32]`，5 拍）与 heqv 流水（ls1/ls2→add→heqv，3 拍 + hv 1 拍）逐 bin 对齐，256/256 bin 与独立 CDF 模型一致（帧尺寸 640×8 时用 RTL 自身 scale ×54>>16 比对）。

### 本轮改动（全部在验证层，未动 RTL）

| 文件 | 改动 |
|---|---|
| `sim/test_pointops.py` | ① 协议改为**单次复位**（帧间不复位，模拟真实流水线跨帧状态）+ 每帧 VSYNC 脉冲 → `FRAME_BLANK=320` 拍帧消隐 → 像素 → `GAP=40`；② PART 2 HISTOGRAM 检查从 vid2 起（vid1 无上一帧，复位锁存 min_r=255/max_r=0 → 输出 255 属正常）；③ 修正 HISTOGRAM 检查的相位：`disp` 取**当前 cycle** 的 `hd`（=stretch(y(T-2))），`y_prev2` 取 `win[0]`（2 拍前锁存的 y），原实现误用 `win[0]` 的历史 hd 导致错位 |
| `sim/verify_pointops.py` | `HistogramModel` 补 **Verilog 宽度提升**模拟：`numerator <= 255*(max_r-min_r)` 中 numerator 为 16 位，减法按 16 位回绕（`0-255=65281`，`255*65281 mod 65536=511`，与 RTL 实测 511 吻合）；`denominator` 为 8 位，减法按 8 位回绕（`0-255=1`）。原模型用 Python 有符号算术，正确协议下（min_r=255/max_r=0 复位锁存）必现 num=-65025 不匹配 |

### 验证结果

```
PART 1: LOG/EMBOSS/HISTOGRAM/HISTOGRAM_EQ 43848 cycles 全部 max_diff=0
PART 2: LOG OK / EMBOSS OK / HISTOGRAM 伪拉伸 35826 像素 OK /
        HIST_EQ ram2 256 bin == CDF(×54>>16) OK
Overall: PASS（仅剩 1 条已知 finding：×54>>16 按 640×480 设计，测试帧 640×8，
        教科书尺度 255*CDF/total 不适用 —— HANDOFF 8-03 已注明非 bug）
run_all.py：11/11 ALL PASS
```

### 遗留（非本次范围）

- 若要把 HIST_EQ 的 ×54>>16 对 640×8 测试帧也对上，需把测试帧改成 640×480 或改 scale——按 8-03 结论此条不算 bug，未动。
- `sim/run_all.py` 的 pointops 流程已由 cocotb 版（`run_pointops_cocotb`）代表，旧 `run_pointops.py`（Verilog dump 版）已废弃，可删。

---

接手优先看这里。上一轮"PART 1 对齐未收敛"的问题已解决：改用 **cocotb 驱动**（读拍前、写拍前、posedge 后比较），四个模块（LOG/EMBOSS/HISTOGRAM/HISTOGRAM_EQ）**43528 周期全部逐周期 max_diff=0**。功能偏差（PART 2）已复核并定位根因，**尚未改 RTL，待用户确认**。

### 新增 / 修改文件

| 文件 | 说明 |
|---|---|
| `sim/tb_pointops_cocotb.v` | 新：最小 cocotb 顶层（只例化四 DUT，无激励） |
| `sim/test_pointops.py` | 新：cocotb 测试，逐周期"驱动→拍前读→模型对比→等沿"，含 PART 2 功能检查 |
| `sim/run_pointops_cocotb.py` | 新：生成 LUT → 编译 → cocotb 运行入口 |
| `sim/verify_pointops.py` | **修改**：修复四个模型与 RTL 不符处（见下），模型现可被 test_pointops 复用 |
| `sim/run_all.py` | 新增第 11 条流程，当前全 11 条 ALL PASS |

### 模型修复清单（验证器问题，非 RTL）

- `HistogramModel`：① `Y0 <= numerator/denominator` 用**拍前** num/den（原实现用拍后，y0 提前一拍）；② `min_r/max_r <= min/max` 锁存用**拍前**极值；③ numerator 用拍前 min_r/max_r。
- `HistEqModel`：① `i_VSYNC_neg` 极性修正为**下降沿**（原实现是上升沿）；② `wea1` 的 `{i_BLANK,r_i_BLANK}==2'b01` 修正为 BLANK **下降沿**（原实现反了）；③ `r_addr_delay` 移入**旧** r_addr（原实现移新值）；④ `hvvr` 移入**旧** hvv；⑤ heqv 恢复为 **3 级流水**（ls1/ls2←旧hv，add←旧ls1+ls2，heqv←旧add>>16，原实现塌缩成一级）；⑥ w_cnt 的 `r_i_BLANK` 条件用拍前值；⑦ `doutb1/doutb2` 无复位（复位期间重读 mem[0]），reset() 置为 ram[0]。

### PART 2 功能偏差（根因已定位，未修 RTL）

1. **HISTOGRAM 拉伸退化为恒等映射**：`min/max` 每帧 rst 清零后重新累积，而 `min_r/max_r` 在 i_VSYNC_neg（第二像素拍）锁存的是**当前帧第一像素**（单像素 A=B）→ num=y、den=1 → 输出恒等。文档要求的"上一帧 min/max 伪拉伸"在"VSYNC 脉冲在帧首"的协议下无法实现。
2. **HISTOGRAM_EQ ram2 映射全错**：
   - 主因：`histogram_value_valid`（扫描窗口）在 VSYNC 脉冲后第 2~257 拍置位——恰好覆盖**帧首 ~255 个像素**，扫描期间 wea1=hvv 把 ram1 清零、hv 累加被像素读污染 → ram2 近乎全 0（均匀帧）或少量饱和值。
   - 即便把 VSYNC 脉冲移到帧尾（扫描落入 gap，CDF 能正确累加到 total=5120），ram2 写地址/数据仍错位（低于 min 的 bin 也拿到非零值）→ `r_addr_delay[39:32]`（5 拍延迟）与 heqv 流水（≈4 拍）不对齐，映射整体右移。对应交接文档 §5-④ 的"组合反馈交叉"嫌疑。
   - 附带：缩放系数 `×54>>16` 按 640×480（307200 像素）设计，测试帧是 640×8，教科书尺度 `255*CDF/total` 必然对不上（此条不算 bug，是帧尺寸假设）。

### 结论与待办

- PART 1（周期精确）✅ 全绿；回归 11/11 PASS。
- 两个功能偏差均指向 HISTOGRAM/HISTOGRAM_EQ 的**帧边界协议**（VSYNC 脉冲相位）与内部时序设计。是否修 RTL、如何修（改模块逻辑 vs 改帧协议）**待用户拍板**——按惯例先确认再改。

---

## ⚠️ 2026-08-03 更新：LOG/EMBOSS/HISTOGRAM/HISTOGRAM_EQ golden 验证已启动，卡在 dump 采样对齐（未 PASS，勿删除中间产物）

**状态**：测试台能编译、能仿真、dump 完整（8 向量 × 5445 拍），LUT 生成与公式核对通过；但 **PART 1 周期精确比对因"dump 行 ↔ 模型周期"未对齐而全部 FAIL**。这是验证层的相位问题，RTL 未做任何改动。上一轮遗留的"四个点运算模块补齐 golden 对照"工作已完成约 70%，接手者重点看 §3 的对齐踩坑记录与 §4 的推荐路线。

### 1. 本次新增文件

| 文件 | 作用 | 状态 |
|------|------|------|
| `sim/ip/behavioral_blk_mem.v` | `blk_mem_gen_0`（256×8 ROM，1 拍读延迟，`$readmemh ip/log_lut.hex`）与 `blk_mem_gen_1`（256×32 简单双口 RAM，写透式写、B 口寄存读、initial 清零）行为模型 | ✅ 编译通过 |
| `sim/gen_pointops_lut.py` | 生成 `sim/ip/log_lut.hex`：`lut[r] = round(255·ln(1+r)/ln(256))`，验证器独立复算同公式（避免循环论证） | ✅ lut[0]=0、lut[255]=255，单调 |
| `sim/tb_pointops.v` | 四个模块共享同一激励并行仿真：8 个确定性向量（vid1~8，含均匀/渐变/LCG 随机）；每向量 `do_reset`（8 拍低电平复位）→ VSYNC 一拍 → 8 行×640 像素 → 320 拍帧间隔（>260，供 HISTOGRAM_EQ 扫完 r_addr）→ 快照 `u_eq.u_ram_2.mem`（`R2` 行）。`C` 行格式（37 字段）：`C vid i_Y0 hsync vsync blank` + LOG 2 + EMBOSS 4 + HISTOGRAM 8 + EQ 16。复位释放后首拍即置 `i_VSYNC=1`（帧起始脉冲） | ✅ 仿真通过 |
| `sim/run_pointops.py` | 一键流程：gen LUT → iverilog 编译（`-g2012 -s tb_pointops`，含两个 blk_mem 模型）→ vvp → verify | ✅ 跑通 |
| `sim/verify_pointops.py` | PART 1：四个周期精确软件副本（`LogModel`/`EmbossModel`/`HistogramModel`/`HistEqModel`，逐寄存器复刻，含 `wea1` 游程逻辑、`w_cnt`、`hvv`/`hvv_r`、×54>>16）；PART 2：功能意图核对（对数公式、浮雕公式、前帧 min/max 拉伸、ram2 vs 真实直方图 CDF） | ❌ PART 1 FAIL（对齐问题） |

**关键发现（此前四模块从未被仿真的根因）**：`blk_mem_gen_0`/`blk_mem_gen_1` 在 `LOG.v`/`HISTOGRAM_EQ.v` 中被例化，但**全仓库（含 `sim/ip/`）无任何定义**。`run_iverilog_all.py` 的 ISP_TOP 流程能过编译，纯粹因为这两个模块未被顶层例化（宏默认路径不含它们）。

### 2. 已确认通过的项

- LUT 生成：`gen_pointops_lut.py` 输出与独立复算一致，lut[0]=0、lut[255]=255、单调递增。
- 编译：`iverilog -g2012` 对 `tb_pointops.v` + 四模块 + 两个 blk_mem 模型零报错（曾修复一处 `EMBOSS #()` 误加参数）。
- dump 完整性：8 向量 × 5445 拍 + `R2` 快照齐全，`sim/pointops_dump.txt` 可复现（LCG 种子 0x12345678，RGB565 打包 `(g>>3)<<11 | (g>>2)<<5 | (g>>3)`）。

### 3. 踩坑记录（dump 输入/输出对齐，三次迭代均未收敛）

| # | tb 驱动方式 | dump 打印 | 结果 | 结论 |
|---|------------|-----------|------|------|
| 1 | `posedge+#1` 阻塞 + 直接打印 `i_Y0` | negedge 打印 | 输出滞后输入一拍（`row0 vsync rtl=1 model=0`） | negedge 打印的输入是下一拍的值 |
| 2 | `negedge+#1` 阻塞/非阻塞 | 同上 | 同 #1 | 驱动时机不是根因 |
| 3 | `posedge+#1` + `c_*` posedge 采样寄存器 | 打印 `c_*` | `em_rY0=22` 等错位 | 采样寄存器引入新相位，且漏算"复位释放到首行 dump 之间的活动周期"（含帧起始 VSYNC 脉冲拍） |

**已确认的事实**：`do_reset` 释放复位后的第一个 posedge 就把 `i_VSYNC` 拉高（见 tb `run_vector`），即 vid 内第 1 活动拍是 VSYNC 脉冲拍；dump 门控要求 `rst_n` 已高（`d_in_flags` 在 posedge 采样），故"dump 首行对应模型第几个 cycle"未钉死。另注意 EMBOSS 的 `display_data` 是组合逻辑，negedge 直接打印会退化为 `threshold`（此时 `r_Y0==i_Y0`），必须用 posedge 采样寄存器捕获真实流水线值。

### 4. 接手者推荐路线（按优先级）

1. **（推荐）改用 cocotb 驱动**：参照 `test_golden.py` 模式写 `test_pointops.py`，`RisingEdge` 后读 post-edge 输出、写 pre-edge 输入，天然对齐，彻底避开 Verilog task 时序陷阱。`verify_pointops.py` 的四个 Model 类可直接复用为周期精确参照。
2. 若坚持 Verilog tb：给 `C` 行加全局拍号列，`$dumpvars` 生成 VCD 用 GTKWave 逐拍对 `u_log.o_*` 与 `i_Y0`，钉死首行 dump 与模型的对应关系。
3. PART 1 全绿后再审 §5 的两处疑似 RTL 问题（**当前结论不可靠，因为比对本身错位**）。

### 5. 疑似 RTL 问题（待对齐后复核，勿直接改 RTL）

- **HISTOGRAM_EQ ram2 映射严重偏离伪均衡**：8 个向量中 74~256/256 个 bin 与独立 CDF 模型不符。代码级嫌疑：① `wea1` 游程计数在命中时 `w_cnt <= 1'b1` 直接归一，段尾游程永不被写回 RAM；② `({i_BLANK, r_i_BLANK} == 2'b01)` 实为 BLANK **上升沿**（项目约定 blank=1 有效），每行起始误写一拍；③ 缩放系数 `(v<<5+v<<4)+(v<<2+v<<1)` = ×54，与 640×480 帧期望的 ≈×255/307200 量级不一致；④ `histogram_value`/`histogram_eq_value` 两个 always 块在 `hvv_r[3]` 拍上存在组合反馈交叉。
- **HISTOGRAM 拉伸输出偏离预期映射**：vid2 出现约 2 万像素差，但其中部分可归因于比对错位（同步信号延迟链相位），需对齐后重判。

### 6. 未完成事项清单（本项）

- [ ] `sim/verify_pointops.py` PART 1 四模块对齐至逐拍 max_diff=0
- [ ] PART 2 复核上述两处疑似 RTL 问题；确认是 bug 则按惯例"修复 + 记录原值"（先问用户）
- [ ] 通过后接入 `run_all.py`（新增流程 11）与 `run_iverilog_all.py`（新增测试 5）——**故意未接入，避免失败流程进回归**

## 📌 2026-08-02 更新：Sobel 阈值→canny_in 路径 + Canny is_edge 验证完成，修复两处 RTL bug ✅

接手优先看这里。本轮补上了交接文档里最后一块未验证路径——Sobel thresh→canny_in→Canny 双阈值+NMS，全部周期级精确匹配（sobel 路径 39754 周期 0 误差，canny 修复后 intended 模型 0 误差）。过程中发现并修复了两处 `canny.v` RTL bug。

### 新增 / 修改文件

| 文件 | 说明 |
|---|---|
| `sim/verify_thresh_path.py` | 新：sobel 阈值路径 + canny is_edge 的周期精确软件副本（复用 verify_golden 的 MatrixGenerator/FWFT/_sqrt20） |
| `sim/run_thresh.py` | 新：编译并运行两个 thresh 测试台 + 调 verifier |
| `sim/tb_sobel_thresh.v` / `sim/tb_canny_thresh.v` | 修改：dump 改 negedge 采样 + posedge 捕获输入标志（d_in_flags），消除 #1 竞态；复位/VSYNC 时序确定性化 |
| `image_processing/Canny_detection/canny.v` | **修复 2 处 RTL bug**（见下） |
| `sim/run_all.py` | 新增第 10 条流程 "Sobel thresh->canny path"，当前全 10 条 ALL PASS |

### 验证结果

```
PART 1: sobel thresh -> canny_in   14 字段 + 3x3 窗口全部 max_diff=0 / 39754 cycles
PART 2: canny is_edge              与修复后 RTL 周期级匹配（intended 模型 0 误差）
Overall: PASS
```

### 发现并修复的 RTL bug（无 git，改前值见注释/本段）

1. **端口方向**：`canny_in` 声明为 `output`，但模块内部只读（喂给 matrix_generator），顶层 ISP_TOP 中它由 sobel 驱动。改为 `input`，否则 iverilog 报 "output port coerced to inout" 无法编译测试台。
2. **phase case 缺 2'b01 分支（关键 bug）**：case 项原本是 00/10/10/11，`2'b10:` 重复、`2'b01:`（45° 分支，比较 m13/m31）缺失 → 弱 + 45° 像素的 `is_edge` 保持旧值。已把第二个 `2'b10:` 改为 `2'b01:`。

### 验证方法

- sobel 路径：软件副本重放 tb 激励（12 组向量：阈值边界 min/max、退化 tmin==tmax、符号翻转、对角线台阶、零梯度），逐周期对比 gx/g/sqrg/phase/thresh/canny_in/3x3 窗口/line/col/同步标志。
- canny 路径：两版模型对照——"as-written"（复刻旧 bug：2'b01 无 case→hold）与"intended"（含 01 分支）。修复前：as-written 全对、intended 仅在弱+phase=01 窗口错 1924 处 → 证实 bug；修复后：intended 全对。

### 写模型时踩到的坑（供后续参考）

- **i_Y0/canny_in 是自由 reg**：复位/VSYNC 期间保持上一帧最后一个值（非 0），模型必须同样馈入，否则帧首窗口错。
- **line/col 语义**：col==639 那拍 col_cnt 回绕为 0、line_cnt+1，每行结尾有两个 `(line+1, col=0)` 标签（回绕拍 + HSYNC 拍）；dump 周期数 = 1(VSYNC) + rows×641。
- **dump 竞态**：posedge+#1 采样与激励 task 的 #1 存在调度竞争 → 改 negedge 采样 + posedge 捕获输入标志；复位释放须在 negedge 后进行，否则多出"半拍幽灵"（rst_n 已拉高但 RTL 状态仍是复位态）。
- **sobel phase 用旧 direction**：phase(T) 的 tie-break 读 direction(T-1)，不是同拍新值；verify_golden 的 Sobel 模型用新 direction 因只对 display 没暴露（本轮 canny_in 对比才暴露，最终模型用旧值全部匹配）。

### 仍可做的后续

- histogram 模块目前只有波形无 golden 对照，可参考本路径方法补验证。
- ISP_TOP 全链路（RGB2YUV→log→histogram→matrix→filter→VGA）端到端仿真。
- 仓库非 git，建议 `git init` 建立版本保护。

**日期**: 2026-07-02（本次更新）
**范围**: 对本仓库的 RGB2YUV 色彩转换 + 高斯/中值/Sobel 滤波器做仿真验证
**工具链**: Icarus Verilog 12.0（`C:\iverilog\bin`，需 `-g2012`）+ Python 3.13 / numpy / cocotb 2.0.1
**结论速览**: RGB2YUV 已确认正确并修复一处精度问题；三个滤波器**算子逻辑正确**；**高斯滤波器流水线已达到周期级精确验证通过**（max_diff=0 / 40690 cycles 0 错误）。详见下文。

---

## 📌 2026-07-02 更新：高斯流水线周期级精确验证通过 ✅

接手优先看这里。本次会话把 `verify_golden.py` 从"教科书 golden + 经验 delay"改写成**周期精确软件副本**，与 RTL 周期对周期 0 误差匹配。

### 验证结果

```
Cycle-by-cycle diff over 40690 cycles:
  max_diff   = 0
  mismatches = 0
>>> PASS: Python model matches RTL exactly, cycle for cycle.
```

6 张测试图像（uniform_050/200、step_v、step_h、gradient、random）全部周期级精确匹配，包括所有边界、过渡带、内部像素。

### 关键根因（推翻 2026-06-28 §8 的"列相位漂移"假设）

之前的 Python 模型违反了 Verilog 非阻塞赋值（NBA）语义：在同一拍内用刚更新的 `gs1/2/3` 去算 `gs_sum`，导致整个流水线提前 1 拍。RTL 实际是 4 级流水线（matrix → gs_1/2/3 → gs_sum → gs_data），每级都用**旧值**。修正 NBA 语义后即周期级匹配。

### 本次改动

**`sim/test_golden.py`**：在每张图像之间加入 `rst_n` 复位（8 拍），让每帧从干净状态开始（`line_cnt=0`、`col_cnt=0`、`r_blank` 清零、FIFO 清空）。修复了之前因 `r_blank[799]` 800 拍展宽导致的跨帧状态污染。

**`sim/verify_golden.py`**：完全重写为周期精确模型。关键设计：
- `GaussianPipeline.clock()` 严格遵循 NBA：所有 RHS 在拍头采样，所有 LHS 在拍尾提交
- `display_data` 是组合逻辑，读**拍前**的 `gs_data`（匹配 Verilog 连续赋值）
- `FWFT_FIFO.step()` 返回**旧** dout（matrix_generator 在本 posedge 看到的值），然后提交更新
- 复刻 testbench 协议：4 拍 warmup → VSYNC → H×W 像素（HSYNC 合并到最后 1 拍）→ 40 拍 blank → 8 拍 inter-image reset → 2000 拍 drain

### 还剩什么

- **Sobel**：用了 CORDIC IP 算 `gx²+gy²` 的平方根，纯 Python 建模成本高，未纳入本验证。
- **Median**：7 级排序网络，可按同样思路建模；RTL dump 已有 `m_disp` 数据，留作后续工作。
- **Canny 阈值路径**（`thresh → canny_in`）：仍未覆盖。

---

## 📌 本轮复核总结（2026-06-28，最新，接手优先看这里）

| 模块 / 项目 | 状态 | 依据 |
|---|---|---|
| RGB2YUV 色彩转换 | ✅ 正确 | 65536 全输入穷举 vs BT.601 浮点，≤1 LSB（§1） |
| RGB565→888 展开 | ✅ 已修复 | 改为标准高位复制（§1.2） |
| 高斯 / 中值 / Sobel **算子** | ✅ 正确 | 均匀场/阶跃/白盒探头三方印证（§2.1） |
| matrix_generator **行延迟** | ✅ **正确（本轮推翻原 bug 结论）** | 白盒双驱动协议、row2..row6 连续正确（§2.3a） |
| 滤波器列方向窗口拼接 | ✅ 正确 | （§6） |
| verify_golden step_h/random FAIL | ⚠️ 非硬件问题 | **根因已精确定位**：`data_valid=i_BLANK\|r_blank[799]` 展宽 + test_golden 每行 641 有效拍 vs col_cnt 640 周期 → 列相位逐行漂移（§8） |
| Sobel thresh→canny_in 路径 | ❓ 未验证 | 待补独立测试（§4.4） |

**一句话**：RTL（含 matrix_generator 行延迟、FIFO 模型）在仿真下均正确，**无需再改 RTL**；step_h/random FAIL 的根因已精确定位为 **test_golden 驱动协议（641 拍/行）与 RTL `col_cnt` 640 周期 + `r_blank[799]` 800 拍展宽的相互作用导致列相位漂移**（§8），属仿真驱动/提取层问题；另有未覆盖的 Canny 阈值路径。

**本轮关键动作**：
1. 复现并**推翻**了原 §2.2"FIFO 行延迟塌缩"——用白盒探头直读 `o_matrix*`，在两种驱动协议下、连续 5 行窗口均正确（10/20/30、20/30/40 …）。
2. 新增回归探头 `sim/tb_rowchange_golden.v`（复刻 `test_golden.py` 每行 641 valid 周期的驱动协议）。
3. 重新生成 `sim/rtl_dump.npz` 并重跑 `verify_golden.py`，确认残留 FAIL 仅出现在 Python 提取层，与 RTL 无关。

---

## 0. 环境备忘（接手第一件事）

- `iverilog`/`vvp` **不在 Git Bash 的 PATH**，位于 `C:\iverilog\bin`。每次开新 shell 要 `export PATH="/c/iverilog/bin:$PATH"`。运行脚本（`run_*.py`）里已硬编码绝对路径 `C:\iverilog\bin\iverilog.exe`。
- 编译滤波器相关 testbench 必须**同时**带上 IP 文件，否则缺模块：
  ```
  iverilog -g2012 -s <top> -o out.vvp \
    sim/ip/behavioral_fifo.v sim/ip/behavioral_cordic.v sim/ip/ip_wrappers.v \
    image_processing/Matrix_generator/matrix_generator.v \
    <filter(s)>.v <tb>.v
  ```
- `RGB2YUV.v` 用了 `16'(R8*77)` 等 SystemVerilog 写法，**必须 `-g2012`**，否则编译报错。
- **本仓库不是 git 仓库**，所有 RTL 改动没有版本回退保护——改前先备份或记下原值（已改动处见 §1.2）。

---

## 1. RGB2YUV —— 已验证正确 ✅

### 1.1 验证方法与结论

模块: `image_processing/RGB_to_YUV/RGB2YUV.v`

做了**两层独立验证**，第二层刻意脱离 RTL 系数避免循环论证：

| 验证 | 方法 | 结果 |
|---|---|---|
| 自校验 testbench | `sim/tb_rgb2yuv_check.v`，参考模型按 RTL 行为写，95 项检查（已知色/随机/连续流/同步延迟） | ✅ 全过 |
| **独立浮点核对** | `sim/verify_rgb2yuv_independent.py`，参考模型用 **BT.601 浮点定义**（非 RTL 系数），穷举**全部 65536** 个 RGB565 输入 | ✅ ≤1 LSB |

独立核对的两个锚点：
- **Fact A**: RTL 整数系数 `77/150/29`、`128/43/85`、`128/107/21` 逐个等于 `round(BT.601浮点 × 256)` → CONFIRMED
- **Fact B**: 全 65536 输入下，RTL 输出 vs BT.601 浮点参考，Y/Cb/Cr 的 max\|diff\| 均 ≤ 1 LSB（仅 `+0/-1` 两档，是定点截断 vs 四舍五入的量化噪声，无系统偏差）

灰点不变量精确成立：黑 `0x0000→(0,128,128)`、白 `0xFFFF→(255,128,128)`。

### 1.2 已做的 RTL 修复（无 git，原值在注释里）

`RGB2YUV.v` 第 45-47 行，RGB565→RGB888 展开从**非标准低位复制**改为**标准高位复制**：

```verilog
// 旧 (低位复制, R5=8 -> R8=64, midtones 偏暗最多 6 LSB)
assign R8 = {i_display_data[15:11], i_display_data[13:11]};
assign G8 = {i_display_data[10:5],  i_display_data[6:5]};
assign B8 = {i_display_data[4:0],   i_display_data[2:0]};
// 新 (标准高位复制, R5=8 -> R8=66 ≈ round(8*255/31))
assign R8 = {i_display_data[15:11], i_display_data[15:13]};
assign G8 = {i_display_data[10:5],  i_display_data[10:9]};
assign B8 = {i_display_data[4:0],   i_display_data[4:2]};
```

修复前/后独立核对对比（同一份 RTL 输出对两种展开的参考）：
```
[canonical (high-bit) 修复后]  max|diff|  Y=1  Cb=1  Cr=1  -> ≤1 LSB OK
[low-bit (pre-fix)     修复前]  max|diff|  Y=5  Cb=6  Cr=6  -> TOO LARGE
```
同步更新了 `sim/tb_rgb2yuv_check.v` 的 `get_R8/G8/B8` 参考函数。

### 1.3 RGB2YUV 相关文件

- `sim/tb_rgb2yuv_check.v` — 自校验 testbench（95 项）
- `sim/tb_rgb2yuv_dump.v` + `sim/rgb2yuv_dump.txt` — 穷举 dump（65536 行）
- `sim/verify_rgb2yuv_independent.py` — 独立 BT.601 核对脚本

---

## 2. 滤波器 —— 算子正确，但发现 matrix_generator 行延迟 bug ⚠️

模块: `image_processing/Gaussian_filter/`、`Median_filter/`、`Sobel_detection/`，共用 `image_processing/Matrix_generator/matrix_generator.v`

### 2.1 算子本身：已确认正确 ✅

三种独立方式证明算子逻辑对（系数/排序/梯度均标准）：
- **均匀场**（uniform_050/200、gradient）：逐像素全对
- **阶跃平滑**（step_v 阶跃附近 cols 318–324）：`0x0000/0x31a6/0xa534/0xdefb` 逐列精确等
- **白盒探头**（`tb_gauss_probe.v`、`tb_filters_window.v`）：给定已知 3×3 窗口，高斯 `gs_sum÷16`、中值、Sobel `sqrg` 全部计算正确

golden 模型（`sim/verify_golden.py` 里的 `gaussian_3x3/median_3x3/sobel_rtl`）用**教科书定义**，不构成循环。

### 2.2 ⚠️ 真实 bug：matrix_generator 行延迟失效

**现象**（白盒铁证，`sim/tb_window_rowchange.v`）：喂三行不同内容
```
row0 = 10...   row1 = 20...   row2 = 30... (当前)
```
在 row2 内部 col 100 探头，正确 3×3 窗口应是 `10/20/30` 三行，RTL 实际给出：
```
window =  30 30 30   ← 应是 10 (row0, 经 fifo_2 延迟2行)
          30 30 30   ← 应是 20 (row1, 经 fifo_1 延迟1行)
          30 30 30   ✓ (row2, 当前)
```
**整个窗口塌缩成当前行，FIFO 本该延迟的历史行没生效。**

**这解释了所有现象**：
| 图像 | 行间内容 | 结果 | 原因 |
|---|---|---|---|
| uniform/gradient/step_v | 每行相同 | ✅ 全对 | FIFO 取不出历史也"恰好"正确 |
| step_h | 仅阶跃处行变化 | 阶跃处错 | 行变化处 bug 暴露 |
| random | 每行都不同 | ❌ 全图错（每行 ~600/638） | bug 无处不在 |

**根因定位**：`matrix_generator.v` 第 222-225 行
```verilog
assign wr_en1 = line_cnt <= 479 && (data_valid | r_i_BLANK[0]);
assign wr_en2 = line_cnt <= 478 && (data_valid | r_i_BLANK[0]);
assign rd_en1 = line_cnt >= 1  && (data_valid | r_i_BLANK[0]);
assign rd_en2 = line_cnt >= 2  && (data_valid | r_i_BLANK[0]);
```
配合 `behavioral_fifo.v` 的 FWFT（First-Word-Fall-Through）行为（第 47-61 行：`count>0 && !dout_valid` 时自动预取，之后每个 `rd_en` 推一个新值）：当 `rd_en` 和 `wr_en` 几乎同时有效，`dout` 实时跟随 `din`，FIFO 没有**真正延迟一整行**，于是跨行窗口的 top/mid 塌缩成当前行。

### 2.3 重要限定：bug 可能与仿真模型有关

此 bug 在**仿真用 `behavioral_fifo.v`**（FWFT 模型）下复现。真实 Xilinx FIFO Generator 的 FWFT 时序可能与 behavioral 模型有差异——因此**"硬件上也错"这一点不敢断言**，只能确认"在此仿真模型下错"。接手者若要下定论，需对照真实 FIFO IP 时序手册（见 §4 建议）。

### 2.3a 更新（2026-06-28 复核）：行延迟 bug **未能复现**，结论推翻 ✅

接手后第一件事就是按 §4.1 复核"行延迟是否为仿真模型所致"。**结论：§2.2 的"FIFO 行延迟塌缩"在当前 RTL + `behavioral_fifo.v` 下完全不复现，窗口逐行正确。**

证据（白盒探头，直读 `matrix_generator` 内部 `o_matrix*`）：

1. **`sim/tb_window_rowchange.v`**（每行 640 valid + HSYNC 处 `i_BLANK=0`）：
   ```
   DURING row2 (val 30), col 100:
     m11..m13 = 10 10 10  (expect 10 10 10)  ✓
     m21..m23 = 20 20 20  (expect 20 20 20)  ✓
     m31..m33 = 30 30 30  (expect 30 30 30)  ✓
   gs_sum=320 gs_data=20  ✓  (高斯 320/16=20 正确)
   ```
   注：HANDOFF §2.2 当时记录的 `30 30 30 / 30 30 30 / 30 30 30`（全塌缩）**无法复现**；现窗口正确分层。该 tb 在 HANDOFF（19:36）之后于 20:11 被修过，疑似当时的 30/30/30 是 tb 测量/驱动方式造成的假象，非 RTL/FIFO 缺陷。

2. **`sim/tb_rowchange_golden.v`**（新增，刻意**完全复刻 `test_golden.py` 的驱动协议**：`i_BLANK` 在 HSYNC 周期仍保持 1，即每行 641 个 valid 周期），探头 row2..row6 稳态：
   ```
   row2 (val30) top=10 mid=20 bot=30  ✓
   row3 (val40) top=20 mid=30 bot=40  ✓
   row4 (val50) top=30 mid=40 bot=50  ✓
   row5 (val60) top=40 mid=50 bot=60  ✓
   row6 (val70) top=50 mid=60 bot=70  ✓
   ```
   两种驱动协议、连续 5 行均正确 → `fifo_1` 真正延迟 1 行、`fifo_2` 真正延迟 2 行，**FWFT 模型下行延迟工作正常，无塌缩**。

**因此**：§2.2 / §4.1 / §7 中"matrix_generator 行延迟 bug（待确认是否仿真模型问题）"**予以撤销**——它既不是 RTL bug，也不是 behavioral_fifo 模型 bug。

**那 `verify_golden.py` 为何在 step_h/random 仍 FAIL？** 重跑（重新生成 `rtl_dump.npz` 后）确认 uniform/gradient/step_v(median)/sobel 多数通过，但 step_h、random 的 Gauss/Median 仍有大 diff。既然白盒证明窗口逐行正确，**剩余 FAIL 只能是 Python 提取/对齐层面的列方向 artefact**（`extract_images_by_in_vsync` 的 `delay` 常量与每行 641 valid 周期、`reshape(h, w+1)[:, :w]` 的边界配合），**不是 FIFO/RTL 缺陷**。后续要让 verify_golden 全绿，应在 Python 提取对齐上下功夫（精确标定每幅图的 row/col 起点），而非改 RTL。


### 2.4 verify_golden.py 的次要问题（非 bug 主因）

`sim/verify_golden.py` 输出提取（第 152-154 行）写死 `delay=5`，实测应为 **7**（`diagnose_step_alignment.py` 证实）。但这**只导致列方向 2 拍偏移**，是 random FAIL 的次要因素；主因是 §2.2 的行延迟 bug。注意 `delay=1`（第 129 行，输入自检）**不能改**，那是正确的。

---

## 3. 本轮产生的文件清单（均在 `sim/`）

### Testbench
| 文件 | 用途 |
|---|---|
| `tb_rgb2yuv_check.v` | RGB2YUV 自校验（95 项） |
| `tb_rgb2yuv_dump.v` | RGB2YUV 全输入穷举 dump |
| `tb_gauss_probe.v` | 高斯内部信号探头（证算子对） |
| `tb_filters_window.v` | 三滤波器白盒窗口验证 |
| `tb_window_rowchange.v` | **抓 matrix_generator bug 的决定性探头** |

### Python 脚本
| 文件 | 用途 |
|---|---|
| `verify_rgb2yuv_independent.py` | RGB2YUV 独立 BT.601 浮点核对（Fact A/B） |
| `verify_filters_aligned.py` | delay=7 的滤波器核对 |
| `verify_filters_final.py` | check A（算子）/check B（全图）双视图 |
| `diagnose_step_alignment.py` | 证 delay=7（step_v 阶跃锚点） |
| `calibrate_row_boundary.py` | row 对齐标定表（揭示 random 全图错） |
| `diagnose_filters_alignment.py` / `diagnose_row_alignment.py` | 早期诊断（后者有 shape bug，参考 `calibrate_row_boundary.py` 代替） |

### 数据
- `rgb2yuv_dump.txt`（983KB，65536 行穷举结果）
- `rgb2yuv_check.vcd` / `gauss_probe.vcd` / `filters_window.vcd` / `window_rowchange.vcd` — 波形

---

## 4. 给接手者的建议（按优先级）

1. **先确认 bug 是否为仿真模型所致**（推荐第一步）：
   - 对照 Xilinx PG057（FIFO Generator FWFT 时序），核对 `behavioral_fifo.v` 的预取/计数行为是否准确
   - 若 `behavioral_fifo.v` 不准 → 修模型重跑，bug 可能消失，则 RTL 在硬件上可能没事
   - 若模型准确 → bug 是真实的，进入第 2 步

2. **修 `matrix_generator.v` 行延迟**（影响面大，高斯/中值/Sobel/Canny 共用）：
   - 核心是让 `fifo_1`/`fifo_2` 真正延迟 1 行/2 行
   - 可能的修法：调整 `rd_en` 使能条件，确保读出的数据滞后写入一整行（640 拍），或改用标准行缓存结构
   - 修复后用 `tb_window_rowchange.v` 回归（窗口应恢复 `10/20/30` 三行）

3. **修 `verify_golden.py`**：第 152-154 行 `delay=5` → `delay=7`（输入自检的 `delay=1` 不动）。修 matrix_generator 后重生成 `rtl_dump.npz` 再核对，理想情况全部 PASS。

4. **Sobel 阈值路径盲区**：`display_data` 用硬编码 `sqrg>120`（sobel.v:199），`thresh_min/thresh_max`（→ `canny_in`）路径从未验证。若关心 Canny，需补独立测试。

---

## 5. 方法论备忘（避免重蹈覆辙）

- **反推有损**：从 RGB565 反推 Y8 会丢低 2 位，曾导致误判"verify_golden 与 RTL 错得一样、构成循环"。定论优先用**白盒探头直读内部信号**，而非端口值的有损反推。
- **过度外推**：曾因 step_h 的 FAIL 集中在边界 2 行，就断言"random 也只是边界 artefact"——被 random 全图错证伪。**不同图像的失败模式要分别验证，不能外推**。
- **循环论证**：参考模型若抄 RTL 系数，则"RTL==参考"对系数是循环的。真正的独立核对要用外部标准（如 BT.601 浮点定义）。
- **穷举优于抽样**：RGB2YUV 用 65536 全输入穷举，彻底消除"只测了几个点"的疑虑。

---

## 6. 已验证为正确的部分（可直接信赖）

- RGB2YUV 色彩转换矩阵（BT.601 定点，全输入 ≤1 LSB）
- RGB2YUV 修复后的标准 RGB565→888 展开
- 高斯 `[1 2 1;2 4 2;1 2 1]/16` 算子逻辑
- 中值 3×3 排序网络算子逻辑
- Sobel `[1 2 1]` 梯度算子逻辑 + `display_data` 二值化（`sqrg>120`）
- 滤波器**列方向**（单行内）3×3 窗口拼接

## 7. 待修 / 待确认

- ~~⚠️ `matrix_generator.v` 行延迟 bug（§2.2）~~ —— **2026-06-28 已复核推翻**（见 §2.3a）。非 RTL bug，非 FIFO 模型 bug，无需改 RTL。
- `verify_golden.py` 残留 step_h/random FAIL：属 **Python 提取/对齐 artefact**（§2.3a），需精确标定每幅图 row/col 起点，而非改 RTL。注 `delay` 已在第 156-158 行设为 7（§2.4 所述待办已完成）。
- Sobel `thresh_min/max`→`canny_in` 路径未验证（§4.4）
- 本轮新增白盒探头：`sim/tb_rowchange_golden.v`（复刻 test_golden 驱动协议 + 多行窗口探头，行延迟回归用）

---

## 8. 二次复核（2026-06-28 21:48）—— step_h/random FAIL 根因精确定位 ✅

§2.3a 把 step_h/random FAIL 归为"Python 提取/对齐 artefact"但**未给出机理**。本轮追到精确根因，**推翻了"只是提取层 artefact"的模糊表述**——根因在驱动协议与 RTL 计数器的相互作用，提取层只是受害者。

### 8.1 根因链

1. **`data_valid` 展宽 800 拍**：`matrix_generator.v:158`
   ```verilog
   assign data_valid = i_BLANK | r_blank[799];
   ```
   `r_blank` 是 803 位移位寄存器（`r_blank <= {r_blank[801:0], i_BLANK}`），`r_blank[799]` 取 799 拍前的 `i_BLANK`。一旦 `i_BLANK` 持续为 1 超过 800 拍，`r_blank[799]` 锁定为 1，`data_valid` 随后**恒为 1 直至 `i_BLANK` 归 0 后再 800 拍**。

2. **test_golden 每行 641 个 `i_BLANK=1` 拍**：`test_golden.py` 每行发 640 像素 + 1 HSYNC 拍，HSYNC 拍 `i_BLANK` 仍为 1（见 `test_golden.py:142-155`）。一帧 10×641=6410 拍 `i_BLANK=1` ≫ 800 → 帧内 `data_valid` 锁死为 1；帧间 `BLANK_GAP_CYCLES=40` ≪ 800 → `data_valid` 在 gap 期间仍为 1，**全程不归 0**。

3. **`col_cnt` 相位逐行漂移**：`matrix_generator.v:207-220`
   ```verilog
   else if (col_cnt == 639) col_cnt <= 10'b0;
   else if(data_valid) col_cnt <= col_cnt + 1'b1;
   ```
   `col_cnt` 以 640 为周期；`data_valid` 全程为 1 → `col_cnt` 全程不停。每行驱动 641 拍，但 `col_cnt` 周期 640 → **每行结束 `col_cnt` 比上一行超前 1**，相位逐行 +1 漂移。

4. **窗口列对齐失配**：RTL 输出"第 r 行 col_cnt=c 处的窗口"实际对应输入第 r 行的列 `(c + r) mod 640`。golden 模型（`verify_golden.py` 的 `gaussian_3x3/median_3x3/sobel_rtl`）按固定列对齐，于是逐行失配。

### 8.2 现象解释（与 verify_golden 输出完全吻合）

| 图像 | 对列漂移的敏感度 | verify_golden 结果 | 解释 |
|---|---|---|---|
| uniform_050/200 | 完全不敏感 | ✅ display diff=0 | 全图同值，任何列漂移无影响 |
| gradient | 列线性，1 拍偏移影响极小 | ✅ display diff=0/32 | 线性输入经高斯/中值平滑仍线性，Sobel 梯度为常数 |
| step_v | 列阶跃处高度敏感 | Gauss ❌(max 8420) / Sobel ❌(65535) / Median ✅ | 阶跃点在 RTL 输出里逐行偏移；中值对单点阶跃取邻域中值，仍为 0 或 220 → 不敏感 |
| step_h | 行变 + 列漂移双重敏感 | ❌ 全错 | 每行内容不同，列漂移直接错位 |
| random | 每像素独立，全敏感 | ❌ 全错(max 46486) | 每行每列都不同，1 拍漂移即全错 |

关键判据：**step_v 的 Median PASS 而 Gauss/Sobel FAIL** 是列漂移的铁证——若是行延迟 bug（§2.2），Median 也会错；若是纯提取 artefact，三者应一起错。只有"列相位漂移 + 中值对单点不敏感"能解释这个分裂。

### 8.3 与 §2.3a 的关系（不矛盾）

§2.3a 用 `tb_rowchange_golden.v` 证明"窗口逐行正确"。该 tb 每行喂**同一值**（feed_row(10)、feed_row(20)…），探头只看 col 100 处的 top/mid/bot 三行值。由于整行同值，**列相位漂移不可见**——无论 col_cnt 落在哪，整行都是同一个数。因此该探头**只能证明 FIFO 行延迟正确**（结论仍成立），**无法暴露列漂移**。两者不矛盾：行延迟 ✅，列相位 ❌（驱动所致）。

### 8.4 非 RTL bug

RTL 在**标准 VGA 时序**下正常：真实 VGA 行消隐期 `i_BLANK=0` 长达 160+ 拍、帧消隐 45 行，`r_blank[799]` 会在消隐期归 0，`data_valid` 正确跟随有效像素，`col_cnt` 每行对齐。问题仅出在 `test_golden.py` 的**紧凑非标准协议**（641 拍/行 + 40 拍短 gap）与 `r_blank[799]` 800 拍展宽的相互作用。**无需改 RTL**。

### 8.5 修复方向（Python 侧，二选一）

**方案 A（推荐）：改 test_golden 驱动协议，让每行有效拍 = 640 整数倍**
- 每行喂 640 拍 `i_BLANK=1`（像素），HSYNC 与第 640 拍**合并**（同拍 `i_HSYNC=1` 且 `i_BLANK=1`），不再单独加 1 拍 HSYNC。这样每行恰好 640 拍 → `col_cnt` 每行整周期对齐，相位不漂移。
- 帧间 gap 需保证下一帧开始时 `line_cnt`/`col_cnt` 回到已知相位。由于 `data_valid` 展宽，gap 期间 `col_cnt` 仍会走；最稳妥是让 gap 足够长使 `line_cnt` 走到 480 归 0（约 `(480-已跑行数)*641` 拍），或改用显式复位每帧重置 RTL（若可接受）。
- 同步改 `verify_golden.py` 的 `extract_images_by_in_vsync`：`h*(w+1)` → `h*w`，`reshape(h, w+1)[:, :w]` → `reshape(h, w)`。
- 验收：`tb_rowchange_golden.v` 仍 PASS（行延迟回归），`verify_golden.py` uniform/gradient/step_v/step_h/random 全绿（含 step_v 的 Gauss/Sobel）。

**方案 B（不推荐）：verify_golden 提取按 RTL col_cnt 相位重映射列**
- 即 golden 第 r 行第 c 列比对 RTL 第 r 行第 `(c - r) mod 640` 列。
- 脆弱：依赖"每行恰好漂移 1"的假设，gap/帧边界处假设易破；且不能修复 step_v 阶跃处 Median 以外的真实数值偏差呈现。仅作理解用。

### 8.6 本轮未改动的文件

仅更新本 HANDOFF。未改任何 RTL / testbench / Python 脚本。`rtl_dump.npz` 为既有产物（可用 `run_golden.py` 重生成）。
