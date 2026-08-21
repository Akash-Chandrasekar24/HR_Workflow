/**
 * Google Apps Script for Dynamic & Flexible Resume Screening Webhook Integration
 * Automatically captures ALL form questions and converts Google Drive PDF/DOCX to Base64
 * so NO Google Service Account is required!
 */

const CONFIG = {
  FASTAPI_WEBHOOK_URL: "https://your-domain.com/api/v1/applications", // Replace with public URL (or ngrok endpoint during dev)
  HMAC_SECRET: "gwc_webhook_sec_8f9a2e3b1c4d7e6f5a0b1c2d3e4f5a6b7c8d9e0f",
  SEND_RESUME_BASE64: true // Automatically sends resume file bytes directly! No GCP Service Account needed!
};

/**
 * Triggered automatically when a candidate submits the Google Form.
 */
function onFormSubmitTrigger(e) {
  try {
    Logger.log("New candidate form submission received.");
    
    let payload = {};
    
    if (e && e.namedValues) {
      payload = parseSheetSubmission(e);
    } else if (e && e.response) {
      payload = parseFormSubmission(e);
    } else {
      Logger.log("No valid event payload detected. Exiting.");
      return;
    }
    
    if (!payload.resume_file_id) {
      Logger.log("ERROR: Candidate submission missing Google Drive resume file ID.");
      return;
    }

    // Attach Base64 encoded file content directly if enabled
    if (CONFIG.SEND_RESUME_BASE64 && payload.resume_file_id) {
      try {
        const file = DriveApp.getFileById(payload.resume_file_id);
        const blob = file.getBlob();
        payload.resume_base64 = Utilities.base64Encode(blob.getBytes());
        payload.resume_filename = file.getName();
        payload.resume_mime_type = blob.getContentType();
        Logger.log("Attached Base64 resume file bytes (" + blob.getBytes().length + " bytes)");
      } catch (fileErr) {
        Logger.log("Could not attach Base64 file bytes: " + fileErr.toString());
      }
    }

    sendWebhookToFastAPI(payload);
    
  } catch (error) {
    Logger.log("ERROR in onFormSubmitTrigger: " + error.toString());
  }
}

/**
 * Parse responses flexibly when trigger is bound to Google Sheets
 */
function parseSheetSubmission(e) {
  const namedValues = e.namedValues;
  const formResponses = {};
  
  for (let key in namedValues) {
    const val = Array.isArray(namedValues[key]) ? namedValues[key][0] : namedValues[key];
    formResponses[key] = val;
  }
  
  const rawResumeUrl = getFlexibleValue(namedValues, ["resume", "cv", "upload", "file", "attach"]);
  const resumeFileId = extractDriveFileId(rawResumeUrl);
  
  return {
    candidate_id: "CAN-" + new Date().getTime(),
    timestamp: new Date().toISOString(),
    full_name: getFlexibleValue(namedValues, ["name", "full name", "candidate name"]) || "Applicant",
    email: getFlexibleValue(namedValues, ["email", "email address", "mail"]) || "applicant@example.com",
    phone: getFlexibleValue(namedValues, ["phone", "contact", "mobile", "cell"]),
    location: getFlexibleValue(namedValues, ["location", "city", "address", "country"]),
    job_role: getFlexibleValue(namedValues, ["job role", "role", "position", "applied for"]) || "PYTHON_DEV",
    years_of_experience: parseFloat(getFlexibleValue(namedValues, ["experience", "years"])) || 0,
    resume_file_id: resumeFileId,
    form_response_id: e.range ? "ROW-" + e.range.getRow() : "RESP-" + new Date().getTime(),
    form_responses: formResponses
  };
}

/**
 * Parse responses flexibly when trigger is bound directly to Google Form
 */
function parseFormSubmission(e) {
  const itemResponses = e.response.getItemResponses();
  const formResponses = {};
  
  let resumeFileId = "";
  let fullName = "Applicant";
  let email = e.response.getRespondentEmail() || "applicant@example.com";
  let phone = "";
  let location = "";
  let jobRole = "PYTHON_DEV";
  let yoe = 0;

  for (let i = 0; i < itemResponses.length; i++) {
    const itemResponse = itemResponses[i];
    const questionTitle = itemResponse.getItem().getTitle();
    const response = itemResponse.getResponse();
    const titleLower = questionTitle.toLowerCase();

    formResponses[questionTitle] = Array.isArray(response) ? response.join(", ") : response;

    if (titleLower.includes("name")) fullName = response;
    else if (titleLower.includes("email")) email = response;
    else if (titleLower.includes("phone") || titleLower.includes("contact")) phone = response;
    else if (titleLower.includes("location") || titleLower.includes("city")) location = response;
    else if (titleLower.includes("role") || titleLower.includes("position")) jobRole = response;
    else if (titleLower.includes("experience")) yoe = parseFloat(response) || 0;
    else if (titleLower.includes("resume") || titleLower.includes("cv") || titleLower.includes("upload") || titleLower.includes("file")) {
      resumeFileId = Array.isArray(response) ? response[0] : extractDriveFileId(response);
    }
  }

  return {
    candidate_id: "CAN-" + new Date().getTime(),
    timestamp: new Date().toISOString(),
    full_name: fullName,
    email: email,
    phone: phone,
    location: location,
    job_role: jobRole,
    years_of_experience: yoe,
    resume_file_id: resumeFileId,
    form_response_id: e.response.getId(),
    form_responses: formResponses
  };
}

function extractDriveFileId(urlOrId) {
  if (!urlOrId) return "";
  if (Array.isArray(urlOrId)) urlOrId = urlOrId[0];
  const match = urlOrId.match(/[-\w]{25,}/);
  return match ? match[0] : urlOrId.trim();
}

function getFlexibleValue(dict, searchKeywords) {
  for (let key in dict) {
    const kLower = key.toLowerCase();
    for (let kw of searchKeywords) {
      if (kLower.includes(kw)) {
        return Array.isArray(dict[key]) ? dict[key][0] : dict[key];
      }
    }
  }
  return "";
}

function sendWebhookToFastAPI(payload) {
  const jsonPayload = JSON.stringify(payload);
  const signatureBytes = Utilities.computeHmacSha256Signature(jsonPayload, CONFIG.HMAC_SECRET);
  const signatureHex = signatureBytes.map(function(b) {
    return ("0" + (b & 0xFF).toString(16)).slice(-2);
  }).join("");

  const options = {
    method: "post",
    contentType: "application/json",
    headers: { "X-Signature-SHA256": signatureHex },
    payload: jsonPayload,
    muteHttpExceptions: true
  };

  UrlFetchApp.fetch(CONFIG.FASTAPI_WEBHOOK_URL, options);
}
