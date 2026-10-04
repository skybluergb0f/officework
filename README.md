# 수변전 일지 웹서비스

Ubuntu 서버에서 실행하고 Windows 브라우저에서 접속하도록 준비 중인 수변전 일지 프로젝트입니다.

## 현재 전달 파일

- `substation-main-log.html`, `substation-main-log.js`: 본관 수변전 일지 인터페이스
- `gangnam-annex-log.html`, `gangnam-annex-log.js`: 강남별관 종합일지 인터페이스
- `test/`: 기존 인터페이스 테스트 파일
- `docs/superpowers/`: 설계 문서와 강남별관 구현 계획
- `excel-workbook-bridge.ps1`, `start-excel-workbook-bridge.bat`: Windows Excel 연동용 보조 파일
- `data/2026년 10월 수변전 일지 - 본관.xlsx`: 서버의 비공개 운영 데이터 폴더에 별도 보관

원본 엑셀과 백업은 Git 저장소에 포함하지 않습니다. `.gitignore`에서 `data/`와 Excel 파일 확장자를 제외합니다.

## 웹서비스

FastAPI 서비스는 Ubuntu의 모든 네트워크 인터페이스(`0.0.0.0:18790`)에서 수신합니다. HTTPS Nginx의 `/substation-log/` 경로도 계속 제공하며, 직접 포트 접속은 HTTP입니다. 인터넷 외부 접속은 서버가 연결된 라우터/상위 방화벽에서 TCP 18790 전달이 설정되어야 합니다. 기록은 필드별 SQLite로 저장합니다. 월별 NAS 엑셀은 처음 조회할 때 읽어 오며, “원본 엑셀 저장 후 인쇄” 동작에서만 백업을 만든 뒤 OOXML 대상 시트 셀을 갱신합니다. 엑셀 동기화에 실패하면 인쇄하지 않습니다. 수기 인쇄는 서버 파일에 쓰지 않습니다.

배포 관련 파일은 `deploy/`에 있습니다. Ubuntu에서 Python 가상환경에 `server/requirements.txt`를 설치하고, `deploy/substation-log-web.service`를 systemd에 등록합니다. `/etc/substation-log-web.env`에는 `SUBSTATION_DB`, `SUBSTATION_WORKBOOK_ROOT`를 설정합니다. `deploy/nginx-rate-limit.conf`는 Nginx `http{}`에, `deploy/nginx-substation-log.conf`는 HTTPS `server{}`에 반영한 뒤 `nginx -t` 성공을 확인하고 reload합니다. Nginx는 요청을 분당 600회, 버스트 100회로 제한해 빠른 자동저장 입력에 여유를 둡니다.

기록 조회·저장·엑셀 동기화 API에는 인증이 없습니다. 공개 주소에 도달할 수 있는 사람은 누구나 일지를 읽고 수정할 수 있으며, 인쇄 버튼을 통해 NAS 엑셀 파일에도 쓸 수 있습니다. 직접 포트 `18790` 접속은 HTTP이므로 전송 구간이 암호화되지 않습니다. 민감 정보는 입력하지 말고, 안전한 외부 접근이 필요하면 HTTPS 도메인을 사용하세요. SQLite, 엑셀 원본과 백업, 설정 파일은 Git에 포함하지 않습니다. 데이터 사본 기반 회귀 테스트는 `python3 -m unittest discover -s server/tests`, 화면 로직 테스트는 `node --test test/*.test.mjs`로 실행합니다.
