package com.launchpilot.service;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

/**
 * 계약 03 ID 규칙. 같은 논리 연산의 재시도는 결정적 ID를 보장해야 한다.
 * - imp/req/msg/appr: 시간 + 카운터 (신규 생성).
 * - brief/cal: thread_id 파생 (결정적, 멱등).
 */
@Component
public class IdGenerator {

    private static final DateTimeFormatter TS =
            DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss");
    private final AtomicLong counter = new AtomicLong();

    /**
     * Create a compact UTC timestamp with a four-digit sequence component.
     *
     * The value combines the current UTC date/time formatted as `yyyyMMdd_HHmmss`,
     * an underscore, and a zero-padded 4-digit counter that cycles through 0000–9999.
     *
     * @return a string in the form yyyyMMdd_HHmmss_0000–9999 representing UTC time and a four-digit sequence number
     */
    private String stamp() {
        return OffsetDateTime.now(ZoneOffset.UTC).format(TS)
                + "_" + String.format("%04d", counter.incrementAndGet() % 10000);
    }

    /**
     * Deprecated internally: generate a run identifier for older local fixtures.
     */
    public String newRunId() {
        return "run_" + stamp();
    }

    /**
     * Generate an import identifier prefixed with "imp_" using the current UTC timestamp and a four-digit counter.
     *
     * @return the import id formatted as "imp_yyyyMMdd_HHmmss_NNNN"
     */
    public String newImportId() {
        return "imp_" + stamp();
    }

    /**
     * Create a new request identifier prefixed with `req_`.
     *
     * @return the identifier in the form req_yyyyMMdd_HHmmss_XXXX where `yyyyMMdd_HHmmss` is the UTC timestamp and `XXXX` is a zero-padded 4-digit counter (0000–9999)
     */
    public String newRequestId() {
        return "req_" + stamp();
    }

    /**
     * Generate a new approval-gate identifier prefixed with "appr_".
     * 승인 게이트는 Java 소유 (계약 01 asyncapi ApprovalGateRequest.approval_id).
     *
     * @return the approval id formatted as "appr_yyyyMMdd_HHmmss_NNNN"
     */
    public String newApprovalId() {
        return "appr_" + stamp();
    }

    /**
     * Generate a new conversation-message identifier prefixed with "msg_".
     * 대화 메시지는 Java가 타임라인에 영속 (계약 01 asyncapi AgentMessage.message_id).
     *
     * @return the message id formatted as "msg_yyyyMMdd_HHmmss_NNNN"
     */
    public String newMessageId() {
        return "msg_" + stamp();
    }

    /**
     * Create a deterministic brief identifier derived from a thread identifier.
     *
     * @param threadId a thread identifier; may include the leading "thread_" prefix
     * @return `brief_<stamp>` where `<stamp>` is the thread id with a leading "thread_" removed if present
     */
    public String briefIdFor(String threadId) {
        return "brief_" + stripRunPrefix(threadId);
    }

    /**
     * Create a deterministic calendar event identifier for a specific experiment row.
     *
     * The returned identifier is formed by removing a leading "thread_" prefix from the provided
     * thread id (if present), prefixing the remainder with "cal_", and appending "_" followed by
     * the supplied index.
     *
     * @param threadId the thread identifier that may start with "run_"
     * @param index the zero-based (or contextual) row/index value to append to the id
     * @return the calendar event id in the form `cal_<threadIdWithoutRunPrefix>_<index>`
     */
    public String calendarEventId(String threadId, int index) {
        return "cal_" + stripRunPrefix(threadId) + "_" + index;
    }

    /**
     * Generate a deterministic post identifier from an import id and CSV row number.
     *
     * @param importId the import identifier expected to begin with "imp_"; the suffix after that prefix is used in the generated id
     * @param rowNumber the CSV row number to include in the generated id
     * @return the post id in the form post_<importSuffix>_<rowNumber>, where <importSuffix> is the part of importId after the "imp_" prefix
     */
    public String postId(String importId, int rowNumber) {
        return "post_" + importId.substring("imp_".length()) + "_" + rowNumber;
    }

    /**
     * Remove a leading "thread_" or "run_" prefix from an identifier, if present.
     *
     * @param threadId the thread identifier which may start with "run_"
     * @return the identifier without the leading "run_" if present, otherwise the original identifier
     */
    private String stripRunPrefix(String threadId) {
        if (threadId.startsWith("thread_")) {
            return threadId.substring("thread_".length());
        }
        return threadId.startsWith("run_") ? threadId.substring("run_".length()) : threadId;
    }
}
