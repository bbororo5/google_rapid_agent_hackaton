package com.launchpilot.api;

import com.launchpilot.dto.common.Channel;
import com.launchpilot.dto.pub.ImportCsvResponse;
import com.launchpilot.service.ApiException;
import com.launchpilot.service.ImportService;
import java.io.IOException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 계약 01: POST /api/import/csv */
@RestController
@RequestMapping("/api/import")
public class ImportController {

    private final ImportService importService;

    /**
     * Creates an ImportController that handles CSV import requests.
     *
     * @param importService the service used to perform CSV imports
     */
    public ImportController(ImportService importService) {
        this.importService = importService;
    }

    /**
     * Handles a multipart CSV upload and imports its contents into the specified workspace and campaign.
     *
     * @param file the uploaded CSV file; must be present and non-empty
     * @param workspaceId identifier of the workspace; must be non-blank
     * @param campaignId identifier of the campaign; must be non-blank
     * @param sourcePlatform optional platform string used to derive the import Channel; blank means no channel
     * @return a ResponseEntity containing the ImportCsvResponse and HTTP status 201 (Created) on success
     * @throws ApiException with a bad-request status when validation fails, the uploaded file cannot be read, or the provided sourcePlatform is invalid
     */
    @PostMapping(value = "/csv", consumes = "multipart/form-data")
    public ResponseEntity<ImportCsvResponse> importCsv(
            @RequestParam("file") MultipartFile file,
            @RequestParam("workspace_id") String workspaceId,
            @RequestParam("campaign_id") String campaignId,
            @RequestParam(value = "source_platform", required = false) String sourcePlatform) {

        if (file == null || file.isEmpty()) {
            throw ApiException.badRequest("file is required and must be non-empty");
        }
        if (!StringUtils.hasText(workspaceId) || !StringUtils.hasText(campaignId)) {
            throw ApiException.badRequest("workspace_id and campaign_id are required");
        }
        Channel channel = parseChannel(sourcePlatform);

        try {
            ImportCsvResponse body = importService.importCsv(
                    file.getInputStream(),
                    StringUtils.hasText(file.getOriginalFilename())
                            ? file.getOriginalFilename() : "upload.csv",
                    workspaceId,
                    campaignId,
                    channel);
            return ResponseEntity.status(HttpStatus.CREATED).body(body);
        } catch (IOException e) {
            throw ApiException.badRequest("could not read uploaded file: " + e.getMessage());
        }
    }

    /**
     * Parse a source platform identifier into a Channel.
     *
     * @param raw the source_platform string; may be null or blank
     * @return the corresponding Channel, or {@code null} if {@code raw} is null or blank
     * @throws ApiException.badRequest if {@code raw} is present but does not map to a valid Channel
     */
    private Channel parseChannel(String raw) {
        if (!StringUtils.hasText(raw)) {
            return null;
        }
        try {
            return Channel.from(raw);
        } catch (IllegalArgumentException e) {
            throw ApiException.badRequest("invalid source_platform: " + raw);
        }
    }
}
