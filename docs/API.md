# API

调用方只依赖下面这些名字。模组自己的 AT 写在 `uart_ble/profiles/` 里。

## 打开串口

```python
open_session(port, baud=None, profile=None, timeout=0.45) -> UartBleSession
```

`profile` 省略时，按注册表依次发探测指令。`"xy-dg02"` 只认这一份。`"raw"` 跳过探测，把串口当成已经配好的透传。

会话支持 `with`，退出时关闭串口。

## 会话

| 方法或属性 | 作用 |
|---|---|
| `name` | 当前广播名 |
| `address` | 模组地址，12 位十六进制 |
| `connection_status` | `ConnectionStatus.CONNECTED` 或 `DISCONNECTED` |
| `is_connected` | 是否已有 BLE 连接 |
| `start_advertising(local_name=None)` | 开始广播。传入 `local_name` 时先改名 |
| `stop_advertising()` | 停止广播 |
| `start_scan(timeout=7.5)` | 扫描一轮，返回 `list[Advertisement]` |
| `stop_scan()` | 提前停止扫描 |
| `disconnect()` | 断开连进来的那一台主机 |
| `discover_services()` | 读取服务 UUID、通知特征、写特征 |
| `write_characteristic(value: bytes)` | 把字节写进透传通道 |
| `read_characteristic(max_bytes=4096, timeout=0.2)` | 读出对端写来的字节 |
| `set_baudrate(baudrate)` | 修改模组串口速率，并改本机串口。这是 pySerial 的概念 |
| `poll(timeout=0)` | 取出连接、断开事件 |

| `send_book(file, protocol="ymodem")` | 在透传链路上发送文件。协议为 xmodem、ymodem、zmodem |
| `recv_book(dest_dir, protocol="ymodem", name="book.bin")` | 接收文件并返回保存路径。XMODEM 使用 `name` |

`Advertisement` 的字段是 `address`、`rssi`、`local_name`、`address_type`。

连接事件的 `link.role` 用 `PeerRole.CENTRAL` 或 `PERIPHERAL`，对应 iOS 的 Central / Peripheral。XY-DG02 上报里，类型 `0` 表示对端是主机。

## 已经连接时

除 `disconnect` 外，AT 指令会抛 `LinkBusy`。这时串口上的字节就是透传数据。

## 传书

`protocol` 取 `xmodem`、`ymodem`、`zmodem`。带 AT 的 profile 必须已经 `is_connected`，否则抛 `UartBleError`。`raw` 把串口视为已经透传。

| 协议 | 文件名 | 长度 | 块 |
|---|---|---|---|
| XMODEM-CRC | 无，调用方给名字 | 收到的是 128 字节填充后的正文 | 128 |
| YMODEM | 第 0 块里的文件名 | 按第 0 块里的长度截断 | 1024 |
| ZMODEM | ZFILE 里的文件名 | 按 ZFILE 里的长度截断 | 1024，控制字节做 ZDLE 转义 |

命令行在透传期间使用：

```powershell
python -m uart_ble send-book --port COM5 book.txt --protocol zmodem
python -m uart_ble recv-book --port COM6 received --protocol zmodem
```

## 增加一种适配器

`define_profile(AtProfileSpec(...))` 注册后即可被 `open_session` 探测到。

`CommandDef`：

| 字段 | 含义 |
|---|---|
| `template` | 指令文本，参数写 `{value}`，不要自己加回车 |
| `response_prefix` | 响应该以这串开头 |
| `accepts_ok` | 收到 `OK` 即成功 |
| `multiline` | 收多行，直到 `end_line` |
| `end_line` | 多行响应的结束行，例如 `+SCAN END` |

身份查询放在 `identity_ops`。SDK 认识这些操作名：

`read_version`、`read_address`、`read_name`、`write_name`、`read_advertising`、`start_advertising`、`stop_advertising`、`start_scan`、`stop_scan`、`read_baudrate`、`set_baudrate`、`read_service`、`read_notify_characteristic`、`read_write_characteristic`、`disconnect`。

模组不支持的操作，调用时抛 `UnsupportedCommand`。
