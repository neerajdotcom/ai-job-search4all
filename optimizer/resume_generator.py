from __future__ import annotations
import io
import re
from typing import Any, Dict, List, Optional
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


def parse_resume_sections(resume_text: str) -> Dict[str, Any]:
    """
    Parses raw resume text into structured sections:
    - name, contact (email, phone, location, links)
    - summary
    - experience (list of {role, company, dates, location, bullets})
    - education (list of {degree, school, year})
    - skills / tools
    - certifications
    """
    if not resume_text or not resume_text.strip():
        return {
            "name": "Candidate",
            "title": "Professional",
            "contact": {},
            "summary": "",
            "experience": [],
            "education": [],
            "skills": [],
            "tools": [],
            "certifications": [],
        }

    raw_lines = [line.strip() for line in resume_text.strip().splitlines() if line.strip()]
    if not raw_lines:
        return {"name": "Candidate", "title": "Professional", "contact": {}, "experience": []}

    # Extract name from top lines (first non-empty line without contact / header keywords)
    name = ""
    for line in raw_lines[:6]:
        clean = line.strip()
        lower = clean.lower()
        if any(k in lower for k in ["resume", "curriculum", "cv", "email", "@", "phone", "http", "linkedin", "github", "contact", "summary", "profile"]):
            continue
        words = clean.split()
        if 1 <= len(words) <= 5 and not any(char in clean for char in ["|", "/", ":", ";", "(", ")"]):
            name = re.sub(r"[^\w\s\.-]", "", clean).strip()
            if len(name) >= 3 and not name.lower().startswith("page "):
                break
    if not name or name.lower() == "candidate":
        # Check email fallback for candidate name (e.g. neerajbanerjee@gmail.com -> Neeraj Banerjee)
        email_m = re.search(r"([\w\.-]+)@[\w\.-]+\.\w+", resume_text)
        if email_m:
            prefix = email_m.group(1).replace(".", " ").replace("_", " ").replace("-", " ")
            prefix_words = [w.capitalize() for w in prefix.split() if w.isalpha()]
            if prefix_words:
                name = " ".join(prefix_words)
        if not name:
            name = re.sub(r"[^\w\s\.-]", "", raw_lines[0]).strip() or "Candidate"

    # Contact extraction
    email_m = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", resume_text)
    phone_m = re.search(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}", resume_text)
    linkedin_m = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\.-]+", resume_text, re.I)
    github_m = re.search(r"(?:https?://)?(?:www\.)?github\.com/[\w\.-]+", resume_text, re.I)
    
    # Location extraction
    location_str = ""
    for line in raw_lines[:8]:
        if any(c in line.lower() for c in ["pune", "mumbai", "bangalore", "delhi", "kolkata", "hyderabad", "london", "new york", "san francisco", "remote", "india", "usa", "uk"]):
            location_str = line.strip(" ,|")
            break

    contact = {
        "email": email_m.group(0) if email_m else "",
        "phone": phone_m.group(0) if phone_m else "",
        "location": location_str,
        "linkedin": linkedin_m.group(0) if linkedin_m else "",
        "github": github_m.group(0) if github_m else "",
    }

    # Section segmentation
    SECTION_HEADERS = {
        "summary": ["summary", "professional summary", "profile", "about me", "executive summary"],
        "experience": ["experience", "work experience", "employment history", "professional experience", "work history"],
        "skills": ["skills", "core competencies", "technical skills", "areas of expertise", "competencies", "skills & tools", "technical environment"],
        "tools": ["tools", "technologies", "software & tools", "platforms", "tech stack"],
        "education": ["education", "academic background", "qualifications", "academics", "academic credentials"],
        "certifications": ["certifications", "licenses", "courses", "certificates", "additional information", "credentials"],
        "projects": ["projects", "key projects", "notable engagements"],
    }

    current_section = "header"
    section_lines: Dict[str, List[str]] = {
        "header": [],
        "summary": [],
        "experience": [],
        "skills": [],
        "tools": [],
        "education": [],
        "certifications": [],
        "projects": [],
    }

    for line in raw_lines:
        lower_line = line.lower().strip(":# -_")
        matched_header = None
        for sec_name, keywords in SECTION_HEADERS.items():
            if lower_line in keywords or any(lower_line.startswith(k + ":") or lower_line.startswith(k + " -") or lower_line == k for k in keywords):
                matched_header = sec_name
                break

        if matched_header:
            current_section = matched_header
            # If line has content after the header (e.g. "ACADEMICS Master in Business..."), retain it
            for kw in SECTION_HEADERS[matched_header]:
                if lower_line.startswith(kw) and len(line) > len(kw) + 3:
                    rest = line[len(kw):].lstrip(" :#-_").strip()
                    if rest:
                        section_lines[current_section].append(rest)
            continue

        section_lines[current_section].append(line)

    # 1. Parse Experience Entries with Robust Bullet Unwrapping
    exp_entries = []
    current_entry = None
    exp_raw_lines = section_lines["experience"]

    if not exp_raw_lines and not section_lines["summary"] and len(raw_lines) > 3:
        # Fallback: if no explicit section headers, treat lines 2..N as body
        exp_raw_lines = raw_lines[2:]

    # Robust Date Regex matching full/abbr months, 4-digit years, and open-ended ranges
    MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Sept?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    date_pattern = re.compile(
        rf"\b(?:{MONTHS}\.?\s+)?(?:\d{{4}}|\d{{2}}/\d{{4}})\s*(?:–|-|—|to)\s*(?:Present|Current|Now|Ongoing|(?:{MONTHS}\.?\s+)?(?:\d{{4}}|\d{{2}}/\d{{4}}))\b",
        re.I
    )

    COMPANY_KEYWORDS = {
        "pvt", "ltd", "inc", "corp", "llc", "solutions", "services", "group", "technologies",
        "technology", "studios", "sdc", "media", "systems", "entertainment", "consulting",
        "corporation", "company", "holdings", "interactive", "digital", "labs", "arrise", "ubisoft", "games2win",
    }
    TITLE_KEYWORDS = {
        "coordinator", "manager", "lead", "executive", "analyst", "associate", "engineer",
        "specialist", "director", "officer", "head", "architect", "consultant", "developer",
        "producer", "scrum", "agile", "founder", "vp",
    }
    SUBHEADER_WORDS = {
        "delivery & production", "process, reporting & stakeholder communication",
        "process, reporting", "stakeholder communication", "key responsibilities",
        "responsibilities", "achievements", "core focus", "technical environment",
    }
    BULLET_PREFIX_RE = re.compile(r"^[-•*–—>\u2022\u2023\u25e6\u2043\u2219]\s*|^\d+[\.\)]\s*")

    for line in exp_raw_lines:
        line_clean_lower = line.strip().lower()
        if line_clean_lower in SUBHEADER_WORDS:
            # Sub-header within an existing job — keep with current entry
            continue

        # Detect embedded section headers that bled into experience
        if any(line_clean_lower.startswith(k) for k in ["academics", "education", "certifications", "additional information", "projects"]):
            if "academic" in line_clean_lower or "education" in line_clean_lower:
                section_lines["education"].append(line)
            elif "project" in line_clean_lower:
                section_lines["projects"].append(line)
            else:
                section_lines["certifications"].append(line)
            continue

        has_date = bool(date_pattern.search(line))
        has_pipe = "|" in line
        is_explicit_bullet = bool(BULLET_PREFIX_RE.match(line.strip()))
        
        # A new job entry header MUST have a date or pipe or explicit company/title marker
        is_header = (not is_explicit_bullet) and (has_date or has_pipe or (not current_entry and len(line) < 80 and any(w in line.lower() for w in TITLE_KEYWORDS | COMPANY_KEYWORDS)))

        if is_header:
            if current_entry:
                exp_entries.append(current_entry)

            date_m = date_pattern.search(line)
            dates = date_m.group(0).strip() if date_m else ""
            clean_line = line.replace(dates, "").strip(" |–-—,()[]") if dates else line

            parts = [p.strip() for p in clean_line.split("|") if p.strip()]
            if len(parts) >= 2:
                p0, p1 = parts[0], parts[1]
                p0_lower_words = set(re.findall(r"\w+", p0.lower()))
                p1_lower_words = set(re.findall(r"\w+", p1.lower()))

                p0_is_co = bool(p0_lower_words & COMPANY_KEYWORDS)
                p1_is_title = bool(p1_lower_words & TITLE_KEYWORDS)
                p0_is_title = bool(p0_lower_words & TITLE_KEYWORDS)

                if (p0_is_co or p1_is_title) and not p0_is_title:
                    company, role = p0, p1
                else:
                    role, company = p0, p1
            elif len(parts) == 1:
                if " at " in clean_line.lower():
                    at_parts = re.split(r"\s+at\s+", clean_line, maxsplit=1, flags=re.I)
                    role, company = at_parts[0].strip(), at_parts[1].strip()
                elif " – " in clean_line and not any(k in clean_line for k in ["PMO", "OTT", "QC", "SDET", "QA"]):
                    dash_parts = clean_line.split(" – ", 1)
                    role, company = dash_parts[0].strip(), dash_parts[1].strip()
                else:
                    role = parts[0]
                    company = ""
            else:
                role = clean_line
                company = ""

            current_entry = {
                "role": role or "Professional Role",
                "company": company,
                "dates": dates,
                "bullets": [],
            }
        else:
            clean_line_text = BULLET_PREFIX_RE.sub("", line).strip()
            if not clean_line_text:
                continue

            if not current_entry:
                current_entry = {
                    "role": "Professional Experience",
                    "company": "",
                    "dates": "",
                    "bullets": [],
                }

            # Line unwrapping logic:
            # If line is an explicit bullet, start a new bullet point.
            # If line is a line-wrapped fragment (e.g. from PDF extraction), join to previous bullet.
            if is_explicit_bullet:
                current_entry["bullets"].append(clean_line_text)
            else:
                # Continuation check: if previous bullet exists and doesn't end with a period,
                # or this line is short (< 80 chars) and lowercase/continuation, merge onto previous bullet.
                if current_entry["bullets"]:
                    prev = current_entry["bullets"][-1].rstrip()
                    if not prev.endswith((".", "!", ";", ":")) or len(clean_line_text) < 40 or clean_line_text[0].islower():
                        current_entry["bullets"][-1] = f"{prev} {clean_line_text}".strip()
                    else:
                        current_entry["bullets"].append(clean_line_text)
                else:
                    current_entry["bullets"].append(clean_line_text)

    if current_entry:
        exp_entries.append(current_entry)

    # Clean up and normalize bullets in all entries (filter out single-word noise or artifacts)
    for entry in exp_entries:
        cleaned_bullets = []
        for b in entry.get("bullets", []):
            b_norm = re.sub(r"\s+", " ", b).strip()
            # Drop single punctuation marks or orphan % symbols
            if len(b_norm) > 5 and not b_norm.startswith("%"):
                cleaned_bullets.append(b_norm)
        entry["bullets"] = cleaned_bullets

    # 2. Parse Skills
    skills_list = []
    for s_line in section_lines["skills"] + section_lines["tools"]:
        clean_s = BULLET_PREFIX_RE.sub("", s_line)
        for item in re.split(r"[,•|/•;]", clean_s):
            item_clean = item.strip()
            if item_clean and 2 < len(item_clean) < 50:
                skills_list.append(item_clean)

    # 3. Parse Education
    edu_list = []
    for e_line in section_lines["education"]:
        clean_e = BULLET_PREFIX_RE.sub("", e_line).strip()
        if clean_e and len(clean_e) > 5:
            edu_list.append(clean_e)

    # 4. Parse Certifications
    certs_list = []
    for c_line in section_lines["certifications"]:
        clean_c = BULLET_PREFIX_RE.sub("", c_line).strip()
        if clean_c and len(clean_c) > 5:
            certs_list.append(clean_c)

    summary_text = " ".join(section_lines["summary"]).strip()

    title = "Professional"
    if len(raw_lines) > 1:
        cand_title = raw_lines[1].strip()
        if len(cand_title) < 60 and not any(char in cand_title for char in ["@", "http", "www", ".com"]):
            title = cand_title

    return {
        "name": name,
        "title": title,
        "contact": contact,
        "summary": summary_text,
        "experience": exp_entries,
        "skills": list(dict.fromkeys(skills_list)),
        "education": edu_list,
        "certifications": certs_list,
    }


def assemble_tailored_resume_data(
    resume_text: str,
    profile_dict: Dict[str, Any],
    tailored_pack: Optional[Dict[str, Any]],
    job: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Assembles a complete, job-specific ATS tailored resume model merging
    candidate ground-truth with role-targeted optimizations.
    """
    parsed = parse_resume_sections(resume_text)

    candidate_name = profile_dict.get("name") or parsed.get("name") or "Candidate"
    target_job_title = job.get("title", "")
    target_company = job.get("company", "")
    candidate_title = profile_dict.get("title") or parsed.get("title") or target_job_title or "Professional"

    # Contact Info
    contact = parsed.get("contact", {})
    email = contact.get("email") or ""
    phone = contact.get("phone") or ""
    location = profile_dict.get("location") or contact.get("location") or ""
    linkedin = contact.get("linkedin") or ""
    github = contact.get("github") or ""

    # Tailored Summary
    summary = ""
    if tailored_pack and tailored_pack.get("optimized_summary"):
        summary = tailored_pack["optimized_summary"]
    elif parsed.get("summary"):
        summary = parsed["summary"]
    else:
        years = profile_dict.get("years_experience", 5)
        summary = (
            f"Results-driven {candidate_title} with over {years} years of proven expertise. "
            f"Specialized in high-velocity delivery, quality assurance, and cross-functional operations "
            f"tailored to high-impact requirements at {target_company}."
        )

    # Core Competencies / Keywords
    competencies = []
    if tailored_pack and tailored_pack.get("optimized_competencies"):
        competencies = tailored_pack["optimized_competencies"]
    elif parsed.get("skills"):
        competencies = parsed["skills"][:12]
    else:
        competencies = [
            "Cross-Functional Leadership",
            "Quality Assurance & QC",
            "Project Management",
            "Process Optimization",
            "Stakeholder Management",
            "Vendor & Resource Management",
        ]

    # Experience with Tailored Bullets
    optimized_bullets_map = tailored_pack.get("optimized_bullets", {}) if tailored_pack else {}
    experience = parsed.get("experience", [])

    structured_experience = []
    for exp in experience:
        role_name = exp.get("role", "")
        company_name = exp.get("company", "")
        dates = exp.get("dates", "")
        original_bullets = exp.get("bullets", [])

        # Match optimized bullets if available for this company/role slug
        tailored_bullets = None
        for k, v in optimized_bullets_map.items():
            if isinstance(v, list) and v and (k.lower() in role_name.lower() or k.lower() in company_name.lower()):
                tailored_bullets = v
                break

        final_bullets = tailored_bullets if tailored_bullets else original_bullets
        if not final_bullets:
            final_bullets = [
                f"Spearheaded operational execution and delivery milestones as {role_name}.",
                "Collaborated with cross-functional teams to optimize delivery cycles and maintain quality standards.",
            ]

        structured_experience.append({
            "role": role_name,
            "company": company_name,
            "dates": dates,
            "bullets": final_bullets,
        })

    # Education & Certifications
    education = parsed.get("education", [])
    certifications = parsed.get("certifications", [])

    # Legacy flat experience lines for backwards-compatibility
    legacy_lines = []
    for exp in structured_experience:
        header = f"{exp['role']}" + (f" | {exp['company']}" if exp.get("company") else "") + (f" ({exp['dates']})" if exp.get("dates") else "")
        legacy_lines.append(header)
        for b in exp.get("bullets", []):
            legacy_lines.append(f"• {b}")

    return {
        "name": candidate_name,
        "title": candidate_title,
        "target_job_title": target_job_title,
        "target_company": target_company,
        "location": location,
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "github": github,
        "summary": summary,
        "competencies": competencies,
        "experience": structured_experience,
        "experience_lines": legacy_lines,
        "education": education,
        "certifications": certifications,
    }


def generate_tailored_docx(resume_data: Dict[str, Any]) -> io.BytesIO:
    """
    Creates a high-contrast, clean ATS-formatted .docx resume.
    """
    doc = Document()

    # Set 0.6 inch standard ATS margins
    for section in doc.sections:
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.65)
        section.right_margin = Inches(0.65)

    # 1. Header: Name & Contact Info
    name_p = doc.add_paragraph()
    name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name_run = name_p.add_run(resume_data.get("name", "Candidate Name"))
    name_run.font.size = Pt(18)
    name_run.font.bold = True
    name_run.font.name = "Calibri"

    contact_parts = []
    if resume_data.get("title"):
        contact_parts.append(resume_data["title"])
    if resume_data.get("location"):
        contact_parts.append(resume_data["location"])
    if resume_data.get("email"):
        contact_parts.append(resume_data["email"])
    if resume_data.get("phone"):
        contact_parts.append(resume_data["phone"])
    if resume_data.get("linkedin"):
        contact_parts.append(resume_data["linkedin"])

    if contact_parts:
        sub_p = doc.add_paragraph(" | ".join(contact_parts))
        sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if sub_p.runs:
            sub_p.runs[0].font.size = Pt(9.5)
            sub_p.runs[0].font.color.rgb = RGBColor(80, 80, 80)

    # Helper for Section Headings
    def add_section_heading(title: str):
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(8)
        h.paragraph_format.space_after = Pt(2)
        run = h.add_run(title.upper())
        run.font.size = Pt(11)
        run.font.bold = True
        run.font.color.rgb = RGBColor(14, 80, 150)
        return h

    # 2. Professional Summary
    if resume_data.get("summary"):
        add_section_heading("Professional Summary")
        p = doc.add_paragraph(resume_data["summary"])
        p.paragraph_format.space_after = Pt(4)
        if p.runs:
            p.runs[0].font.size = Pt(10)

    # 3. Core Competencies & Keywords
    if resume_data.get("competencies"):
        add_section_heading("Core Competencies & Expertise")
        comp_text = " • ".join(resume_data["competencies"])
        p = doc.add_paragraph(comp_text)
        p.paragraph_format.space_after = Pt(4)
        if p.runs:
            p.runs[0].font.size = Pt(9.5)

    # 4. Professional Experience
    if resume_data.get("experience"):
        add_section_heading("Professional Experience")
        for exp in resume_data["experience"]:
            role_p = doc.add_paragraph()
            role_p.paragraph_format.space_before = Pt(4)
            role_p.paragraph_format.space_after = Pt(1)

            role_run = role_p.add_run(exp.get("role", "Role"))
            role_run.font.bold = True
            role_run.font.size = Pt(10.5)

            if exp.get("company"):
                co_run = role_p.add_run(f" | {exp['company']}")
                co_run.font.size = Pt(10)
                co_run.font.color.rgb = RGBColor(60, 60, 60)

            if exp.get("dates"):
                dt_run = role_p.add_run(f"  ({exp['dates']})")
                dt_run.font.size = Pt(9.5)
                dt_run.font.italic = True
                dt_run.font.color.rgb = RGBColor(100, 100, 100)

            for bullet in exp.get("bullets", []):
                bp = doc.add_paragraph(style="List Bullet")
                bp.paragraph_format.space_before = Pt(1)
                bp.paragraph_format.space_after = Pt(1)
                brun = bp.add_run(bullet)
                brun.font.size = Pt(9.5)

    # 5. Education
    if resume_data.get("education"):
        add_section_heading("Education & Credentials")
        for edu in resume_data["education"]:
            p = doc.add_paragraph(edu)
            p.paragraph_format.space_after = Pt(2)
            if p.runs:
                p.runs[0].font.size = Pt(9.5)

    # 6. Certifications
    if resume_data.get("certifications"):
        add_section_heading("Certifications & Training")
        for cert in resume_data["certifications"]:
            p = doc.add_paragraph(cert)
            p.paragraph_format.space_after = Pt(2)
            if p.runs:
                p.runs[0].font.size = Pt(9.5)

    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output


def generate_tailored_pdf(resume_data: Dict[str, Any]) -> io.BytesIO:
    """
    Generates a clean, professional, ATS-formatted PDF tailored résumé using ReportLab.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = HexColor("#0f172a")
    secondary_color = HexColor("#334155")
    accent_color = HexColor("#0d9488")
    muted_color = HexColor("#64748b")

    name_style = ParagraphStyle(
        "CandidateName",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        textColor=primary_color,
        spaceAfter=2,
    )

    title_style = ParagraphStyle(
        "CandidateTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        alignment=TA_CENTER,
        textColor=accent_color,
        spaceAfter=3,
    )

    contact_style = ParagraphStyle(
        "ContactInfo",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=muted_color,
        spaceAfter=8,
    )

    section_heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=primary_color,
        spaceBefore=8,
        spaceAfter=2,
    )

    body_style = ParagraphStyle(
        "BodyTextCustom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=secondary_color,
        spaceAfter=4,
    )

    role_style = ParagraphStyle(
        "RoleTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=primary_color,
        spaceBefore=4,
        spaceAfter=1,
    )

    bullet_style = ParagraphStyle(
        "BulletCustom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12.5,
        textColor=secondary_color,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=2,
    )

    story = []

    # 1. Header: Name, Title, Contact
    story.append(Paragraph(resume_data.get("name", "Candidate Name"), name_style))
    if resume_data.get("title"):
        story.append(Paragraph(resume_data["title"], title_style))

    contact_parts = []
    contact = resume_data.get("contact", {})
    if contact.get("email"): contact_parts.append(contact["email"])
    if contact.get("phone"): contact_parts.append(contact["phone"])
    if contact.get("location"): contact_parts.append(contact["location"])
    if contact.get("linkedin"): contact_parts.append(contact["linkedin"])

    if contact_parts:
        story.append(Paragraph(" &bull; ".join(contact_parts), contact_style))

    def add_pdf_section(title: str):
        story.append(Spacer(1, 4))
        story.append(Paragraph(title.upper(), section_heading_style))
        story.append(HRFlowable(width="100%", thickness=0.75, color=accent_color, spaceAfter=4, spaceBefore=1))

    # 2. Summary
    if resume_data.get("summary"):
        add_pdf_section("Professional Summary")
        story.append(Paragraph(resume_data["summary"], body_style))

    # 3. Core Competencies
    if resume_data.get("competencies"):
        add_pdf_section("Core Competencies & Expertise")
        story.append(Paragraph(" &bull; ".join(resume_data["competencies"]), body_style))

    # 4. Professional Experience
    if resume_data.get("experience"):
        add_pdf_section("Professional Experience")
        for exp in resume_data["experience"]:
            role_text = f"<b>{exp.get('role', 'Role')}</b>"
            if exp.get("company"):
                role_text += f" | {exp['company']}"
            if exp.get("dates"):
                role_text += f" <font color='#64748b'>({exp['dates']})</font>"
            story.append(Paragraph(role_text, role_style))

            for bullet in exp.get("bullets", []):
                clean_b = re.sub(r"^[-•*–—>\u2022\u2023\u25e6\u2043\u2219\d\.\)]+\s*", "", bullet).strip()
                if len(clean_b) > 4:
                    story.append(Paragraph(f"&bull; {clean_b}", bullet_style))

    # 5. Education
    if resume_data.get("education"):
        add_pdf_section("Education & Credentials")
        for edu in resume_data["education"]:
            clean_edu = re.sub(r"^[-•*–—>\u2022\u2023\u25e6\u2043\u2219\d\.\)]+\s*", "", edu).strip()
            if len(clean_edu) > 4:
                story.append(Paragraph(clean_edu, body_style))

    # 6. Certifications
    if resume_data.get("certifications"):
        add_pdf_section("Certifications & Training")
        for cert in resume_data["certifications"]:
            clean_cert = re.sub(r"^[-•*–—>\u2022\u2023\u25e6\u2043\u2219\d\.\)]+\s*", "", cert).strip()
            if len(clean_cert) > 4:
                story.append(Paragraph(clean_cert, body_style))

    doc.build(story)
    buffer.seek(0)
    return buffer


