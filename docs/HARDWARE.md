# USB 하드웨어 연결

두 펌웨어는 시리얼 명령을 받고 USB HID 마우스 리포트를 전송합니다. 독자적인 반복 매크로를 MCU에 저장하지 않습니다. PC가 다음 명령을 보내지 않으면 추가 클릭을 생성하지 않습니다. 펌웨어는 초안 구현이며 실제 보드에서 컴파일/업로드/입력 검증을 수행해야 합니다.

## Arduino Leonardo / Micro

1. Arduino IDE에서 ATmega32u4 기반 Leonardo 또는 Micro 보드를 선택합니다. 일반 Uno용 코드가 아닙니다.
2. `firmware/ArcMouseLeonardo/ArcMouseLeonardo.ino`를 엽니다. Arduino의 `Mouse` 라이브러리를 사용합니다.
3. 선택적으로 누름 버튼을 **D2와 GND 사이**에 연결합니다. 내부 풀업을 사용하며 누르는 동안 ARM/입력 명령을 거부합니다.
4. 보드에 업로드한 후 USB 케이블을 다시 연결합니다.
5. 장치 관리자의 CDC COM 포트를 확인합니다.

Leonardo의 USB Mouse 동작은 [Arduino 공식 문서](https://docs.arduino.cc/language-reference/en/functions/usb/Mouse/)를 참고하세요.

## Raspberry Pi Pico

1. 보드에 맞는 CircuitPython을 설치합니다. 일반 MicroPython 펌웨어와 다른 환경입니다.
2. 해당 CircuitPython 버전에 맞는 Adafruit 라이브러리 번들의 `adafruit_hid` 폴더를 `CIRCUITPY/lib`에 넣습니다.
3. `firmware/pico/boot.py`와 `code.py`를 `CIRCUITPY` 루트에 복사하고 전원을 다시 연결합니다.
4. 선택적으로 누름 버튼을 **GP2와 GND 사이**에 연결합니다.
5. 설정에서는 **CDC data 포트**를 사용합니다. console 포트와 혼동하면 handshake에 실패합니다. 포트가 연속 번호라고 가정하지 마세요.

[CircuitPython usb_cdc 문서](https://docs.circuitpython.org/en/latest/shared-bindings/usb_cdc/)에 따르면 Windows에서는 console/data 스트림이 별도 COM 포트로 표시됩니다. HID API는 [Adafruit 공식 문서](https://docs.circuitpython.org/projects/hid/en/latest/api.html#adafruit_hid.mouse.Mouse)를 참고하세요.

## 앱 설정

```powershell
python -m pip install -r requirements-hardware.txt
python main.py
```

1. MCU를 연결하지 않은 상태에서 추가 설정의 HID 장치 목록을 확인합니다.
2. MCU를 연결하고 추가 설정 창을 다시 열어 새로 나타난 마우스 HID 경로를 확인합니다.
3. **USB 보드 (Leonardo / Pico)**를 선택하고 COM 포트와 해당 HID 경로를 지정합니다.
4. 추가 설정의 **입력 없이 테스트**를 켜면 시리얼 포트를 열지 않습니다. 실제 보드 연결 검증은 테스트 옵션을 끄고, 외부 동작이 없는 창에서 반복 횟수를 3회로 설정해 진행합니다.
5. 실제 마우스를 움직이면 입력이 멈추는지, 비상 정지 단축키와 물리 정지 버튼이 작동하는지 확인합니다.

HID 경로와 COM 포트의 자동 연관 추론은 구현하지 않았습니다. 실제 마우스를 제외 장치로 고르면 그 마우스의 입력을 무시하게 됩니다. 보드 재연결/포트 변경 후에는 다시 선택하세요. 잘못된 COM 포트는 `HELLO` handshake에서 중단하며, 다른 장치의 VID/PID를 사칭하지 않습니다.

## ARCMOUSE/1 프로토콜

115200 baud, ASCII, 한 줄당 최대 63바이트, LF 종결입니다. 호스트는 정확한 sequence의 응답을 받은 후 다음 명령을 보냅니다. 응답이 150 ms 안에 오지 않으면 오류로 중단합니다. 보드 리셋을 고려해 포트 연결 후 2초 동안 취소 가능한 대기를 합니다.

| 명령 | 응답 | 의미 |
|---|---|---|
| `1 HELLO` | `1 ARCMOUSE/1` | 식별, 버튼 해제, disarm |
| `2 ARM` | `2 OK` | 다음 입력 허용; 정지 버튼을 누르면 거절 |
| `3 MOVE 10 -5` | `3 OK` | 상대 HID 이동; 각 축 -127~127 |
| `4 CLICK 1` | `4 OK` | 왼쪽 버튼; 2는 오른쪽, 4는 가운데 |
| `0 STOP` | `0 OK` | 모든 버튼 해제 및 disarm |

호스트는 각각의 MOVE/CLICK 전에 ARM을 보냅니다. 장시간 대기로 watchdog이 disarm한 경우 다음 의도된 입력만 다시 허용하기 위함입니다. MCU는 마지막 유효 입력/ARM 후 150 ms가 지나면 모든 버튼을 해제하고 disarm합니다. CLICK은 5 ms 누른 뒤 해제하며, 해제 후 ACK를 보냅니다. 이미 USB 스택에 제출된 한 건의 이벤트까지 취소할 수 있는 것은 아닙니다.

펌웨어의 핀 입력은 물리 버튼의 전기적 상태를 확인하는 소프트웨어 로직입니다. watchdog도 펌웨어 루프에서 처리하므로 펌웨어 자체가 정지하면 150 ms 처리를 보장하지 않습니다. 실제 배포 전에 보드별 USB 동작, 단선/재연결, 버튼 오작동, CPU 부하 상황을 검증해야 합니다.

## 상대 HID 좌표

일반 USB 마우스 리포트는 상대 이동입니다. Windows의 포인터 가속에 영향을 받으므로 PC는 실제 커서 위치를 다시 읽어 작은 보정 이동을 보냅니다. 100회 안에 목표에서 ±1 px로 수렴하지 않으면 중단합니다. 포인터를 중앙에 고정하는 게임, 독점 Raw Input, 특정 앱의 ClipCursor 환경에는 적합하지 않을 수 있습니다. MCU 이동은 직렬 왕복 지연 때문에 소프트웨어 모드보다 느릴 수 있습니다.

## 실기 점검표

- [ ] 컴파일/펌웨어 업로드 성공
- [ ] USB HID 마우스와 CDC 포트가 정상적으로 나타남
- [ ] HELLO/ARM/STOP 정상 및 잘못된 명령 거부
- [ ] 상대 이동의 방향/크기, 각 버튼 동작
- [ ] USB 분리 및 호스트 강제 종료 후 추가 클릭 없음
- [ ] 물리 정지 버튼을 누르는 동안 입력 없음
- [ ] ACK 유실 시 호스트 중단
- [ ] 실제 마우스/키보드 개입 시 0.5초 양보
- [ ] DPI/다중 모니터/가속 설정별 좌표 수렴
