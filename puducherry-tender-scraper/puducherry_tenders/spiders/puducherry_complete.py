import re
from datetime import datetime

import scrapy


class PuducherryCompleteTendersSpider(scrapy.Spider):
    """
    Comprehensive spider for extracting all tender details from Puducherry tenders website.
    Handles variable table structures (12-13 tablebg tables) by identifying fields based on labels.
    """
    name = "puducherry_complete_tenders"
    state_name = "Puducherry"
    start_urls = [
        "https://pudutenders.gov.in/nicgep/app?page=FrontEndTendersByOrganisation&service=page",
    ]

    @staticmethod
    def _clean_text(value: str) -> str:
        """Clean text by removing newlines and extra whitespace."""
        if value is None:
            return None
        # Replace newlines with space and normalize whitespace
        cleaned = re.sub(r'\s+', ' ', value.replace('\n', ' ').replace('\r', ' '))
        return cleaned.strip()

    @classmethod
    def _clean_listing_title(cls, value: str):
        """Clean a tender title taken from the listing page.

        Listing anchors wrap the title in square brackets, e.g.
        "[Campus Management System]". Strip those wrappers and normalise
        whitespace so the title matches the detail-page value.
        """
        cleaned = cls._clean_text(value)
        if not cleaned:
            return cleaned
        if cleaned.startswith('[') and cleaned.endswith(']'):
            cleaned = cleaned[1:-1].strip()
        return cleaned

    @staticmethod
    def _parse_numeric(value: str, *, as_int: bool = False):
        """Parse numeric values from strings, handling common formats."""
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        lowered = cleaned.lower()
        if lowered in {"na", "nil", "n/a", "--", "not applicable"}:
            return None
        # Remove currency symbols, commas, and other non-numeric characters
        normalized = re.sub(r"[^0-9.\-]", "", cleaned.replace(",", ""))
        if not normalized or normalized == '.':
            return None
        try:
            number = float(normalized)
        except ValueError:
            return None
        return int(number) if as_int else number

    @staticmethod
    def _parse_datetime(value: str):
        """Parse datetime values from various formats."""
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        # Common date formats used in the website
        for fmt in (
            "%d-%b-%Y %I:%M %p",
            "%d-%b-%Y %H:%M",
            "%d-%b-%Y",
            "%d/%m/%Y %I:%M %p",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
        ):
            try:
                parsed = datetime.strptime(cleaned, fmt)
                return parsed.isoformat()
            except ValueError:
                continue
        return None

    def _extract_field_value(self, table, field_label):
        """
        Extract field value from a table based on its label.
        Searches for td containing the label and returns the value from the next td.
        """
        # Try to find the label in any td
        for row in table.css('tr'):
            tds = row.css('td')
            for i, td in enumerate(tds):
                text = ''.join(td.css('::text').getall()).strip()
                if field_label.lower() in text.lower():
                    # Value is usually in the next td
                    if i + 1 < len(tds):
                        value = ''.join(tds[i + 1].css('::text').getall()).strip()
                        return self._clean_text(value) if value else None
        return None

    def parse(self, response):
        """Parse organization listing page."""
        rows = response.css('tr.even, tr.odd')
        state_name = response.meta.get('state', self.state_name)
        self.logger.info(f'[{state_name}] Found {len(rows)} organizations to parse')
        
        for row in rows:
            try:
                tds = row.css('td')
                org_name = tds[1].css('::text').get()
                link = tds[2].css('a::attr(href)').get()
                count = tds[2].css('a::text').get()

                if link:
                    absolute_link = response.urljoin(link)
                    yield scrapy.Request(
                        absolute_link,
                        callback=self.parse_tenders,
                        meta={
                            'state': state_name,
                            'start_url': response.meta.get('start_url', response.url),
                            'organization_name': org_name.strip() if org_name else '',
                            'tender_count': int(count.strip()) if count and count.strip().isdigit() else 0
                        }
                    )
            except Exception as e:
                self.logger.error(f'Error parsing organization row: {e}')
                continue

    def parse_tenders(self, response):
        """Parse the tenders listing for a specific organization."""
        org_name = response.meta.get('organization_name', '')
        tender_rows = response.css('tr.even, tr.odd')
        state_name = response.meta.get('state', self.state_name)
        self.logger.info(f'[{state_name}] Found {len(tender_rows)} tenders for organization: {org_name}')
        
        for row in tender_rows:
            try:
                tds = row.css('td')
                
                if len(tds) >= 5:
                    e_published_date = tds[1].css('::text').get()
                    closing_date = tds[2].css('::text').get()
                    opening_date = tds[3].css('::text').get()
                    title_link = tds[4].css('a::attr(href)').get()
                    title_text = self._clean_listing_title(tds[4].css('a::text').get())
                    ref_no = tds[4].css('::text').getall()
                    full_title = ' '.join([t.strip() for t in ref_no if t.strip()])
                    organisation_chain = tds[5].css('::text').get() if len(tds) > 5 else ''
                    
                    if title_link:
                        absolute_tender_link = response.urljoin(title_link)
                        yield scrapy.Request(
                            absolute_tender_link,
                            callback=self.parse_tender_detail,
                            meta={
                                'state': state_name,
                                'start_url': response.meta.get('start_url', response.url),
                                'organization_name': org_name,
                                'e_published_date': self._clean_text(e_published_date) if e_published_date else '',
                                'closing_date': self._clean_text(closing_date) if closing_date else '',
                                'opening_date': self._clean_text(opening_date) if opening_date else '',
                                'title': title_text if title_text else '',
                                'title_full': self._clean_text(full_title) if full_title else '',
                                'tender_link': absolute_tender_link,
                                'organisation_chain': self._clean_text(organisation_chain) if organisation_chain else ''
                            }
                        )
            except Exception as e:
                self.logger.error(f'Error parsing tender row: {e}')
                continue

    def parse_tender_detail(self, response):
        """
        Comprehensive parsing of tender detail page.
        Extracts all available fields from all tablebg tables dynamically.
        """
        try:
            tender_data = {
                'state': response.meta.get('state', ''),
                'organization_name': response.meta.get('organization_name', ''),
                'e_published_date': response.meta.get('e_published_date', ''),
                'closing_date': response.meta.get('closing_date', ''),
                'opening_date': response.meta.get('opening_date', ''),
                'title': response.meta.get('title', ''),
                'organisation_chain': response.meta.get('organisation_chain', '')
            }
            
            # Get all tablebg tables
            tablebg_tables = response.css('table.tablebg')
            self.logger.info(f'Found {len(tablebg_tables)} tablebg tables on page: {response.url}')
            
            # Define comprehensive field mappings for extraction
            field_mappings = {
                # Basic tender information
                'tender_reference_number': ['Tender Reference Number', 'Ref Number', 'Reference No'],
                'tender_id': ['Tender ID', 'e-Tender ID'],
                'tender_type': ['Tender Type'],
                'tender_category': ['Tender Category', 'Form of Contract'],
                'tender_form': ['Form of Contract'],
                'title': ['Title'],
                
                # Dates
                'published_date': ['e-Published Date', 'Published Date'],
                'bid_submission_start_date': ['Bid Submission Start Date', 'Document Download / Sale Start Date', 'Document Download/Sale Start Date'],
                'bid_submission_end_date': ['Bid Submission End Date', 'Document Download / Sale End Date', 'Document Download/Sale End Date', 'Closing Date'],
                'bid_opening_date': ['Bid Opening Date', 'Technical Bid Opening Date', 'Opening Date'],
                'document_download_start': ['Document Download Start Date', 'Document Download/Sale Start Date'],
                'document_download_end': ['Document Download End Date', 'Document Download/Sale End Date'],
                'clarification_start_date': ['Clarification Start Date', 'Seek Clarification Start Date'],
                'clarification_end_date': ['Clarification End Date', 'Seek Clarification End Date'],
                'pre_bid_meeting_date': ['Pre-Bid Meeting Date', 'Pre Bid Meeting Date'],
                'period_of_sale': ['Period of Sale of Tender Document'],
                
                # Tender financial details
                'tender_value': ['Tender Value', 'Tender Value in ₹', 'Tender Value in Rs'],
                'estimated_cost': ['Estimated Cost'],
                'earnest_money_deposit': ['Earnest Money Deposit', 'EMD Amount'],
                'contract_value': ['Contract Value'],
                
                # Tender fee
                'tender_fee': ['Tender Fee', 'Cost of Tender Document'],
                'fee_payable_to': ['Fee Payable To', 'Tender Fee Payable To'],
                'fee_payable_at': ['Fee Payable At', 'Tender Fee Payable At'],
                'tender_fee_exemption_allowed': ['Tender Fee Exemption Allowed'],
                
                # EMD details
                'emd_amount': ['EMD Amount', 'Earnest Money Deposit'],
                'emd_exemption_allowed': ['EMD Exemption Allowed'],
                'emd_fee_type': ['EMD Fee Type', 'EMD Through'],
                'emd_percentage': ['EMD Percentage', 'EMD in percentage'],
                'emd_payable_to': ['EMD Payable To'],
                'emd_payable_at': ['EMD Payable At'],
                'bg_required': ['BG Required', 'BG/ Exemption Allowed', 'BG/Exemption Allowed'],
                'ebg_required': ['eBG Required'],
                'minimum_direct_emd_payment': ['Min. Direct EMD Payment', 'Minimum Direct EMD Payment'],
                
                # Bid validity and contract
                'bid_validity_days': ['Bid Validity(Days)', 'Bid Validity', 'Bid Validity (Days)'],
                'bid_validity_period': ['Period of Work', 'Work Completion Period'],
                'period_of_work_days': ['Period Of Work(Days)', 'Period of Work (Days)'],
                'contract_type': ['Contract Type'],
                
                # Work details
                'work_description': ['Work Description', 'Work/ Item(s)', 'Work/Item(s)'],
                'location': ['Location', 'Place of Work'],
                'pincode': ['Pincode', 'Pin Code'],
                'pre_qualification': ['Pre Qualification Details', 'Pre-Qualification Details'],
                'nda_pre_qualification': ['NDA/Pre Qualification', 'NDA Pre Qualification'],
                'independent_external_monitor_remarks': ['Independent External Monitor/Remarks', 'Independent External Monitor Remarks'],
                
                # Pre-bid meeting details
                'pre_bid_meeting_place': ['Pre Bid Meeting Place', 'Pre-Bid Meeting Place'],
                'pre_bid_meeting_address': ['Pre Bid Meeting Address', 'Pre-Bid Meeting Address'],
                'bid_opening_place': ['Bid Opening Place'],
                
                # Product category
                'product_category': ['Product Category'],
                'sub_category': ['Sub Category', 'Sub category'],
                
                # Other details
                'time_allowed': ['Time Allowed for Completion'],
                'extension_period': ['Extension Period'],
                'model_of_contract': ['Model of Contract'],
                'multi_currency_allowed': ['Multi-Currency Allowed'],
                'payment_mode': ['Payment Mode'],
                'credit_period': ['Credit Period'],
                'covering_emd': ['Covering EMD'],
                'msme_exemption': ['MSE Exemption Allowed', 'MSME Exemption'],
                'startup_exemption': ['Startup Exemption Allowed'],
                'should_allow_nda_tender': ['Should Allow NDA Tender'],
                'allow_preferential_bidder': ['Allow Preferential Bidder'],
                
                # Additional fields that might be present
                'no_of_covers': ['No. Of Covers', 'Number of Covers'],
                'no_of_packets': ['No. of Packets(Offline)'],
                'contract_period': ['Contract Period'],
                'service_category': ['Service Category'],
                'nature_of_work': ['Nature of Work'],
                'eligibility_criteria': ['Eligibility Criteria'],
                'withdrawal_allowed': ['Withdrawal Allowed'],
            }
            
            # Extract fields from all tablebg tables
            # Fields that can be overridden from detail page.
            # NOTE: 'title' is intentionally NOT overridden here. The detail page
            # has multiple tables containing the word "Title" (e.g. document/cover
            # listings), and the override loop lets the last match win, which
            # clobbers the real title with stray values like "S.No". The listing
            # page anchor already provides the authoritative title.
            override_fields = {'work_description'}
            
            for table in tablebg_tables:
                for field_key, field_labels in field_mappings.items():
                    # Skip if field already has a value (unless it's an override field)
                    if tender_data.get(field_key) and field_key not in override_fields:
                        continue
                    
                    # Try each label variant
                    for label in field_labels:
                        value = self._extract_field_value(table, label)
                        if value:
                            tender_data[field_key] = value
                            break
            
            # Extract payment/instruction table (list_table) - only bank names
            list_tables = response.css('table.list_table')
            if list_tables:
                first_list_table = list_tables[0]
                all_rows = first_list_table.css('tr')
                data_rows = all_rows[1:] if len(all_rows) > 1 else []
                
                pmt_instr_table = []
                for row in data_rows:
                    tds = row.css('td')
                    # Only take the second column (bank name)
                    if len(tds) >= 2:
                        bank_name = tds[1].css('::text').get()
                        if bank_name and bank_name.strip():
                            pmt_instr_table.append(bank_name.strip())
                
                tender_data['pmt_instr_table'] = pmt_instr_table
            else:
                tender_data['pmt_instr_table'] = []
            
            # Extract Tender Inviting Authority (TIA) details
            # Look for "Name" and "Address" fields in additional_fields or tables
            for table in tablebg_tables:
                # Try to find Name field
                if 'tia_name' not in tender_data or not tender_data.get('tia_name'):
                    name_value = self._extract_field_value(table, 'Name')
                    if name_value:
                        tender_data['tia_name'] = name_value
                
                # Try to find Address field
                if 'tia_address' not in tender_data or not tender_data.get('tia_address'):
                    address_value = self._extract_field_value(table, 'Address')
                    if address_value:
                        tender_data['tia_address'] = address_value
            
            # Extract form of contract and other contract details
            for table in tablebg_tables:
                if 'form_of_contract' not in tender_data or not tender_data.get('form_of_contract'):
                    form_value = self._extract_field_value(table, 'Form of Contract')
                    if form_value:
                        tender_data['form_of_contract'] = form_value
                
                if 'general_technical_evaluation_allowed' not in tender_data or not tender_data.get('general_technical_evaluation_allowed'):
                    gte_value = self._extract_field_value(table, 'General Technical Evaluation Allowed')
                    if gte_value:
                        tender_data['general_technical_evaluation_allowed'] = gte_value
                
                if 'itemwise_technical_evaluation_allowed' not in tender_data or not tender_data.get('itemwise_technical_evaluation_allowed'):
                    ite_value = self._extract_field_value(table, 'Item Wise Technical Evaluation Allowed')
                    if ite_value:
                        tender_data['itemwise_technical_evaluation_allowed'] = ite_value
                
                if 'is_multi_currency_allowed_for_boq' not in tender_data or not tender_data.get('is_multi_currency_allowed_for_boq'):
                    mc_boq_value = self._extract_field_value(table, 'Is Multi Currency Allowed For BOQ')
                    if mc_boq_value:
                        tender_data['is_multi_currency_allowed_for_boq'] = mc_boq_value
                
                if 'is_multi_currency_allowed_for_fee' not in tender_data or not tender_data.get('is_multi_currency_allowed_for_fee'):
                    mc_fee_value = self._extract_field_value(table, 'Is Multi Currency Allowed For Fee')
                    if mc_fee_value:
                        tender_data['is_multi_currency_allowed_for_fee'] = mc_fee_value
                
                if 'allow_two_stage_bidding' not in tender_data or not tender_data.get('allow_two_stage_bidding'):
                    two_stage_value = self._extract_field_value(table, 'Allow Two Stage Bidding')
                    if two_stage_value:
                        tender_data['allow_two_stage_bidding'] = two_stage_value
                
                if 'document_download_sale_start_date' not in tender_data or not tender_data.get('document_download_sale_start_date'):
                    doc_start_value = self._extract_field_value(table, 'Document Download/Sale Start Date')
                    if doc_start_value:
                        tender_data['document_download_sale_start_date'] = doc_start_value
                
                if 'document_download_sale_end_date' not in tender_data or not tender_data.get('document_download_sale_end_date'):
                    doc_end_value = self._extract_field_value(table, 'Document Download/Sale End Date')
                    if doc_end_value:
                        tender_data['document_download_sale_end_date'] = doc_end_value
            
            # Parse numeric fields
            numeric_fields = [
                'tender_fee', 'tender_value', 'emd_amount'
            ]
            for field in numeric_fields:
                if field in tender_data and tender_data[field]:
                    tender_data[field] = self._parse_numeric(tender_data[field])
            
            # Parse integer fields
            integer_fields = ['bid_validity_days']
            for field in integer_fields:
                if field in tender_data and tender_data[field]:
                    tender_data[field] = self._parse_numeric(tender_data[field], as_int=True)
            
            # Parse datetime fields
            datetime_fields = [
                'published_date', 'bid_opening_date', 'bid_submission_start_date',
                'bid_submission_end_date', 'clarification_start_date', 'clarification_end_date', 
                'pre_bid_meeting_date', 'e_published_date', 'closing_date', 'opening_date',
                'document_download_sale_start_date', 'document_download_sale_end_date'
            ]
            for field in datetime_fields:
                if field in tender_data and tender_data[field]:
                    tender_data[field] = self._parse_datetime(tender_data[field])
            
            # Define the exact schema - only these fields will be kept
            schema_fields = [
                'state', 'organization_name', 'e_published_date', 'closing_date', 'opening_date',
                'title', 'organisation_chain', 'tender_reference_number', 'tender_id', 'tender_type',
                'tender_category', 'payment_mode', 'withdrawal_allowed', 'sub_category', 'tender_fee',
                'fee_payable_to', 'fee_payable_at', 'tender_fee_exemption_allowed', 'emd_amount',
                'emd_exemption_allowed', 'emd_fee_type', 'emd_percentage', 'emd_payable_to',
                'emd_payable_at', 'pre_bid_meeting_date', 'tender_value', 'bid_validity_days',
                'period_of_work_days', 'contract_type', 'work_description', 'location', 'pincode',
                'nda_pre_qualification', 'independent_external_monitor_remarks', 'pre_bid_meeting_place',
                'pre_bid_meeting_address', 'bid_opening_place', 'product_category',
                'should_allow_nda_tender', 'allow_preferential_bidder', 'published_date',
                'bid_submission_start_date', 'bid_submission_end_date', 'bid_opening_date',
                'clarification_start_date', 'clarification_end_date', 'form_of_contract',
                'general_technical_evaluation_allowed', 'itemwise_technical_evaluation_allowed',
                'is_multi_currency_allowed_for_boq', 'is_multi_currency_allowed_for_fee',
                'allow_two_stage_bidding', 'tender_fee_in', 'emd_amount_in',
                'document_download_sale_start_date', 'document_download_sale_end_date',
                'notice_inviting_tender', 'pmt_instr_table', 'tia_name', 'tia_address'
            ]
            
            # Create final output with only schema fields
            final_data = {}
            for field in schema_fields:
                final_data[field] = tender_data.get(field, None)
            
            self.logger.info(f'Successfully extracted tender data: {final_data.get("tender_reference_number", "Unknown")}')
            yield final_data
            
        except Exception as e:
            self.logger.error(f'Error parsing tender detail page: {e}')
            # Yield basic data with schema fields even if detail extraction fails
            yield {
                'state': response.meta.get('state', None),
                'organization_name': response.meta.get('organization_name', None),
                'e_published_date': self._parse_datetime(response.meta.get('e_published_date', '')),
                'closing_date': self._parse_datetime(response.meta.get('closing_date', '')),
                'opening_date': self._parse_datetime(response.meta.get('opening_date', '')),
                'title': response.meta.get('title', None),
                'organisation_chain': response.meta.get('organisation_chain', None),
                'tender_reference_number': None,
                'tender_id': None,
                'tender_type': None,
                'tender_category': None,
                'payment_mode': None,
                'withdrawal_allowed': None,
                'sub_category': None,
                'tender_fee': None,
                'fee_payable_to': None,
                'fee_payable_at': None,
                'tender_fee_exemption_allowed': None,
                'emd_amount': None,
                'emd_exemption_allowed': None,
                'emd_fee_type': None,
                'emd_percentage': None,
                'emd_payable_to': None,
                'emd_payable_at': None,
                'pre_bid_meeting_date': None,
                'tender_value': None,
                'bid_validity_days': None,
                'period_of_work_days': None,
                'contract_type': None,
                'work_description': None,
                'location': None,
                'pincode': None,
                'nda_pre_qualification': None,
                'independent_external_monitor_remarks': None,
                'pre_bid_meeting_place': None,
                'pre_bid_meeting_address': None,
                'bid_opening_place': None,
                'product_category': None,
                'should_allow_nda_tender': None,
                'allow_preferential_bidder': None,
                'published_date': None,
                'bid_submission_start_date': None,
                'bid_submission_end_date': None,
                'bid_opening_date': None,
                'clarification_start_date': None,
                'clarification_end_date': None,
                'form_of_contract': None,
                'general_technical_evaluation_allowed': None,
                'itemwise_technical_evaluation_allowed': None,
                'is_multi_currency_allowed_for_boq': None,
                'is_multi_currency_allowed_for_fee': None,
                'allow_two_stage_bidding': None,
                'tender_fee_in': None,
                'emd_amount_in': None,
                'document_download_sale_start_date': None,
                'document_download_sale_end_date': None,
                'notice_inviting_tender': None,
                'pmt_instr_table': None,
                'tia_name': None,
                'tia_address': None,
                'error': str(e)
            }


# Usage:
# scrapy crawl puducherry_complete_tenders -O puducherry_complete.json
