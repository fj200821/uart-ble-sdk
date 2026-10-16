# UART BLE SDK

主机侧的串口透传 BLE 适配器库。串口进来，对外的动词和 Android、iOS、Windows 的 BLE API 对齐。换一块模组时，只加一份 profile，不改调用方。

当前内置新一 **XY-DG02**（ASR5601，手册 V1.1.5）。广播和扫描已在 Windows + CH340、115200 上核对过。

## 安装

需要 Python 3.11+。

```powershell
pip install -e .
python -m unittest discover -s tests -t .
```

## 命令行

```powershell
python -m uart_ble ports
python -m uart_ble info --port COM5
python -m uart_ble scan --port COM5
python -m uart_ble setup --port COM5 --name XY-DG02
```

`info` 打开串口并识别模组。`scan` 扫一轮附近广播。`setup` 调用 `start_advertising`。

## 程序里用

```python
from uart_ble import open_session

with open_session("COM5") as session:
    print(session.name, session.address)
    session.start_advertising(local_name="XY-DG02")
    found = session.start_scan()
    session.write_characteristic(b"hello")
    data = session.read_characteristic()
```

`open_session` 只打开串口，对应 pySerial 的 `open`。手机连上模组之后，`session.connection_status` 才是 `connected`。

## 和系统 BLE API 的对应

| 这个 SDK | Android | iOS | Windows |
|---|---|---|---|
| `start_advertising` | `startAdvertising` | `startAdvertising` | `StartAdvertising` |
| `stop_advertising` | `stopAdvertising` | `stopAdvertising` | `StopAdvertising` |
| `start_scan` | `startScan` | `scanForPeripherals` | `BluetoothLEAdvertisementWatcher.Start` |
| `stop_scan` | `stopScan` | `stopScan` | `Stop` |
| `name` | `getName` | `name` | `Name` |
| `address` | `getAddress` | 外设地址 | `BluetoothAddress` |
| `disconnect` | `disconnect` | `cancelPeripheralConnection` | 关闭设备 |
| `connection_status` | `STATE_CONNECTED` | `didConnect` | `ConnectionStatus` |
| `discover_services` | `discoverServices` | `discoverServices` | `GetGattServicesForUuidAsync` |
| `write_characteristic` | `writeCharacteristic` | `writeValue` | `WriteValueAsync` |
| `read_characteristic` | `readCharacteristic` | `readValue` | `ReadValueAsync` |

## XY-DG02 能做什么

从机广播，默认服务 `FFF0`。手机写入 `FFF2`，数据从模组串口出来。串口写入的数据，经 `FFF1` 通知给手机。

从机同时只接受 **1 台主机**。主机模式最多再连接 **4 台从机**。两边可以同时挂着，没有 `AT+ROLE` 这种开关。

| 动作 | 模组指令 |
|---|---|
| 开始广播 | `AT+ADV=1` |
| 停止广播 | `AT+ADV=0` |
| 扫描约 6 秒 | `AT+SCAN=1` |
| 连接一台从机 | `AT+CONN=<地址>,<类型>` |
| 断开连进来的主机 | `AT+DISCONN=1` |
| 断开自己连出去的从机 | `AT+DISCONN=0` |

地址类型 `0` 是静态地址，`1` 是随机地址。类型为 `0` 时可以省略。

已经有连接时，串口是透传，扫描和改广播这些指令发不出去，要先 `disconnect()`。串口只有一路，多条链路同时在线时，字节分给哪一条，模块手册没有定义。115200 下透传大约 10 KB/s。广播名最长 20 字节。

## 换一块模组

新模组实现同一批动词即可。探测串是只读指令，自动识别时谁先匹配用谁。`raw` 没有 AT，字节原样进出，不参与自动识别。

```python
from uart_ble import define_profile, open_session
from uart_ble.profile import AtProfileSpec, CommandDef

define_profile(AtProfileSpec(
    profile_id="acme",
    display_name="ACME",
    default_baud=9600,
    probe_command="AT+ID?",
    probe_prefix="+ID:",
    commands={
        "read_version": CommandDef("AT+ID?", response_prefix="+ID:"),
        "write_name": CommandDef("AT+N={value}", accepts_ok=True),
        "start_advertising": CommandDef("AT+A=1", accepts_ok=True),
        "start_scan": CommandDef(
            "AT+SCAN",
            response_prefix="+SCAN:",
            multiline=True,
            end_line="+SCAN END",
        ),
    },
    identity_ops=("read_version",),
))
```

更细的接口说明见 [docs/API.md](docs/API.md)。

## 许可

[MIT](LICENSE)。XY-DG02 的模组固件不属于本仓库。
