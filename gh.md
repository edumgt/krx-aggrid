# gh 명령어 실행 기록

## 0-1. gh CLI 설치 (Ubuntu/Debian 기준)
```bash
sudo apt update
sudo apt install -y gh
```

## 0-2. gh 로그인 인증
```bash
gh auth login
```
    
## 1. gh 설치 여부 확인
```bash
which gh && gh --version
```

## 2. gh 로그인 사용자 확인
```bash
gh auth status
```

## 3. 내 repo 목록 5개 조회
```bash
gh repo list edumgt --limit 5
```

## 4. public 저장소 생성 (test1010)
```bash
gh repo create test1010 --public
```

## 5. repository Actions secret 생성 (test1111 repo, VVV=1111)
```bash
gh secret set vvv --body "1111" --repo edumgt/test1111
```

## 6. Codespaces 환경 (참고)
Yahoo Finance 파이프라인으로 전환되어 별도의 API 키나 Secret 설정이 필요하지 않습니다.

## 7. secret 목록 확인
```bash
gh secret list --repo edumgt/test1111
```
