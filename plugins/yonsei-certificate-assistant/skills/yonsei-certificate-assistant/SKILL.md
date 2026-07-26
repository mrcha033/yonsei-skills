---
name: yonsei-certificate-assistant
description: Select and complete an official Yonsei University certificate issuance route on macOS, distinguish an electronically signed original from a paper original or copy, and diagnose the portal certificate entry. Use for Yonsei transcripts, enrollment or graduation certificates, Mac printing limitations, electronic PDF delivery, original verification, kiosk, postal, or Government24 alternatives.
---

# Yonsei Certificate Assistant

Use an official issuance path. Do not bypass print controls, intercept a print spool, use a virtual printer against the site's restrictions, remove verification marks, or describe a protected screenshot as an original.

## Workflow

1. Establish the recipient's requirement:
   - Choose the official electronic certificate when an electronically signed PDF original is accepted.
   - Choose an official paper route when the recipient requires a paper original.
2. Validate the packaged entry:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" doctor
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe certificate --json
   ```

3. For issuance, open the Yonsei Portal, authenticate in the browser, and select **인터넷증명서 → 전자증명서발급** or the supported paper send/print option. The pre-login direct URL is verification-only.
4. Show the document type, language, delivery method, quantity, fee, and destination immediately before any paid issuance, email delegation, or postal request. Continue only after the user explicitly confirms those exact values.
5. Keep the issued document and verification data out of chat. Save or transmit it only to the location the user explicitly selects.

## Paper-original fallback

When macOS cannot use the legacy print module, use a supported Windows environment with a real authorized printer, a campus kiosk or service desk, postal issuance, or Government24 as applicable. Do not convert an electronic certificate to paper and label it a paper original.

## Authentication and network boundary

Never request a Yonsei password, OTP, certificate number, or payment detail in chat. Use the official browser login. Direct HTTPS reachability does not prove that every authenticated issuance step works without an internal network; diagnose an authenticated failure before concluding that a VPN is required, and do not launch a VPN client from this skill.

Official references:

- `https://www.yonsei.ac.kr/sc/405/subview.do`
- `https://sswy.yonsei.ac.kr/sswy/board/notice.do?articleNo=219018&attachNo=179887&mode=download`
