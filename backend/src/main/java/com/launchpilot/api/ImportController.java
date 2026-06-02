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

    public ImportController(ImportService importService) {
        this.importService = importService;
    }

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
