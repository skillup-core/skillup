# 게시판 만드는 법

게시판은 **목록 폼**과 **상세 폼** 두 개의 JSON 파일로 구성됩니다.

- **목록 폼**: `board` 타입 필드 하나를 가진 폼. 레코드 목록을 표 형식으로 표시합니다.
- **상세 폼**: 레코드 하나를 읽고 쓰는 일반 폼. 목록에서 행을 클릭하면 열립니다.

두 파일은 목록 폼의 `detailFormPath` 속성으로 연결됩니다.

## 1단계: 상세 폼 만들기

상세 폼은 레코드 하나의 내용을 보여주는 일반 폼입니다.

**필드 구성 (건의하기 예시):**

| 필드 ID | 타입 | 설명 |
|---|---|---|
| `title` | `text` | 제목 입력란 |
| `body` | `textarea` | 본문 (마크다운 지원) |
| `f3` | `dropdown` | 상태 (New / Review / Resolved ...) |
| `f12` | `info` | 시스템 필드 `@row_id` 표시 |
| `f13` | `info` | 시스템 필드 `@author` 표시 |
| `f14` | `info` | 시스템 필드 `@created_at` 표시 |
| `f16` | `comment` | 댓글 영역 |

**버튼은 `boardCommand` 속성으로 동작을 지정합니다:**

| `boardCommand` | 동작 |
|---|---|
| `POST` | 새 레코드 등록 |
| `MODIFY` | 현재 레코드 수정 |
| `DELETE` | 현재 레코드 삭제 |
| `LIST` | 목록으로 돌아가기 |

**시스템 필드** (`@row_id`, `@author`, `@created_at` 등)는 `info` 타입 필드의 `infoField` 속성에 지정하면 자동으로 값이 채워집니다.

## 2단계: 목록 폼 만들기

목록 폼은 `board` 타입 필드 하나만 있으면 됩니다.

**핵심 속성:**

```json
{
  "id": "board1",
  "type": "board",
  "detailFormPath": "desktop/board/suggest/form/detail.json",
  "listColumns": [
    { "id": "@row_id",     "width": "8"    },
    { "id": "@author",     "width": "15"   },
    { "id": "@created_at", "width": "15"   },
    { "id": "f3",          "width": "8"    },
    { "id": "title",       "width": "rest" }
  ]
}
```

- `detailFormPath`: 상세 폼 JSON의 경로 (프로젝트 루트 기준)
- `listColumns`: 목록에 표시할 컬럼과 너비. **상세 폼에 정의된 필드 ID** 또는 시스템 필드 ID를 사용합니다.

## 컬럼 너비 지정 방법

| 값 | 의미 |
|---|---|
| 숫자 (예: `"15"`) | 전체 너비의 15% |
| `"rest"` | 나머지 공간을 모두 차지 (한 컬럼에만 사용) |

## 권한 설정

`permission` 속성으로 읽기/쓰기/댓글/수정 권한을 제어합니다.

```json
"permission": {
  "groupName": "FEEDBACK",
  "read":    { "nonMember": true },
  "write":   { "member": true    },
  "comment": { "member": true    },
  "modify":  { "admin": true     }
}
```

| 권한 | 설명 |
|---|---|
| `read` | 목록 및 상세 내용 조회 |
| `write` | 새 레코드 등록 및 본인 글 수정/삭제 |
| `comment` | 댓글 작성 |
| `modify` | 다른 사람 글 수정/삭제, 권한 변경 |

`nonMember: true`로 설정하면 로그인하지 않아도 조회할 수 있습니다.
