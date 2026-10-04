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

## 현재 상태

Ubuntu용 웹 서버/API 구현 전 단계입니다. Windows Excel COM 브리지는 Ubuntu 서버에서 실행할 수 없으므로, 서비스 구현 시 서버측 Excel 파일 읽기·쓰기 방식으로 대체해야 합니다.
