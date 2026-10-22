/**
 * COMPREHENSIVE RESPONSE CODE MAPPINGS
 * Includes all possible keywords for Live, Charged, and Declined statuses
 */

export const RESPONSE_CODES = {
    // ==================== SESSION/TOKEN ERRORS ====================
    'FAILED_TO_GET_SESSION_TOKEN': { status: 'Error', message: 'Session Token Failed - Retry' },
    'SESSION_TOKEN_MISSING': { status: 'Error', message: 'Session Token Missing' },
    'SESSION_EXPIRED': { status: 'Error', message: 'Session Expired - Retry' },
    'INVALID_SESSION': { status: 'Error', message: 'Invalid Session - Retry' },
    'SESSION_NOT_FOUND': { status: 'Error', message: 'Session Not Found - Retry' },
    
    // ==================== CAPTCHA ERRORS ====================
    'CAPTCHA_REQUIRED': { status: 'Error', message: 'CAPTCHA Required' },
    'CAPTCHA_METADATA_MISSING': { status: 'Error', message: 'Site Dead (CAPTCHA) - Wait 40min' },
    'CAPTCHA_INVALID': { status: 'Error', message: 'CAPTCHA Invalid - Retry' },
    'CAPTCHA_EXPIRED': { status: 'Error', message: 'CAPTCHA Expired - Retry' },
    'CAPTCHA_FAILED': { status: 'Error', message: 'CAPTCHA Failed - Retry' },
    
    // ==================== CCN LIVE (Card is Valid but Issue with Details) ====================
    // CVV/CVC Mismatch
    'INCORRECT_CVC': { status: 'Live', message: 'CCN Live ✓ (CVV Mismatch)' },
    'incorrect_cvc': { status: 'Live', message: 'CCN Live ✓ (CVV Mismatch)' },
    'CVV_MISMATCH': { status: 'Live', message: 'CCN Live ✓ (CVV Mismatch)' },
    'INVALID_CVC': { status: 'Live', message: 'CCN Live ✓ (CVV Mismatch)' },
    'INCORRECT_CVV': { status: 'Live', message: 'CCN Live ✓ (CVV Mismatch)' },
    'SECURITY_CODE_INVALID': { status: 'Live', message: 'CCN Live ✓ (CVV Mismatch)' },
    'CVC_CHECK_FAILED': { status: 'Live', message: 'CCN Live ✓ (CVV Mismatch)' },
    
    // AVS/ZIP Mismatch
    'INCORRECT_ZIP': { status: 'Live', message: 'CCN Live ✓ (ZIP Mismatch)' },
    'incorrect_zip': { status: 'Live', message: 'CCN Live ✓ (ZIP Mismatch)' },
    'AVS_MISMATCH': { status: 'Live', message: 'CCN Live ✓ (AVS Mismatch)' },
    'INCORRECT_ADDRESS': { status: 'Live', message: 'CCN Live ✓ (Address Mismatch)' },
    'ADDRESS_VERIFICATION_FAILED': { status: 'Live', message: 'CCN Live ✓ (AVS Failed)' },
    'POSTAL_CODE_INVALID': { status: 'Live', message: 'CCN Live ✓ (ZIP Invalid)' },
    'AVS_FAILED': { status: 'Live', message: 'CCN Live ✓ (AVS Failed)' },
    'ZIP_CODE_INVALID': { status: 'Live', message: 'CCN Live ✓ (ZIP Invalid)' },
    
    // Insufficient Funds (Card is valid but no money)
    'INSUFFICIENT_FUNDS': { status: 'Live', message: 'CCN Live ✓ (Insufficient Funds)' },
    'INSUFFICIENT_BALANCE': { status: 'Live', message: 'CCN Live ✓ (Insufficient Funds)' },
    'NOT_SUFFICIENT_FUNDS': { status: 'Live', message: 'CCN Live ✓ (Insufficient Funds)' },
    'BALANCE_INSUFFICIENT': { status: 'Live', message: 'CCN Live ✓ (Low Balance)' },
    'EXCEEDS_BALANCE': { status: 'Live', message: 'CCN Live ✓ (Exceeds Balance)' },
    
    // Card Number Issues (but card exists)
    'INCORRECT_NUMBER': { status: 'Live', message: 'CCN Live ✓ (Number Mismatch)' },
    'CARD_NUMBER_INCORRECT': { status: 'Live', message: 'CCN Live ✓ (Number Mismatch)' },
    
    // ==================== CHARGED/SUCCESS ====================
    'ProcessedReceipt': { status: 'Charged', message: '✓ Charged Successfully' },
    'thank_you': { status: 'Charged', message: '✓ Order Confirmed' },
    'SUCCESS': { status: 'Charged', message: '✓ Payment Approved' },
    'APPROVED': { status: 'Charged', message: '✓ Payment Approved' },
    'PAYMENT_COMPLETE': { status: 'Charged', message: '✓ Payment Complete' },
    'ORDER_CONFIRMED': { status: 'Charged', message: '✓ Order Confirmed' },
    'TRANSACTION_APPROVED': { status: 'Charged', message: '✓ Transaction Approved' },
    'PAYMENT_SUCCESSFUL': { status: 'Charged', message: '✓ Payment Successful' },
    'CHARGE_SUCCEEDED': { status: 'Charged', message: '✓ Charge Succeeded' },
    'COMPLETED': { status: 'Charged', message: '✓ Transaction Completed' },
    
    // ==================== DECLINED (Card Rejected) ====================
    // Generic Declines
    'CARD_DECLINED': { status: 'Declined', message: '✗ Card Declined' },
    'GENERIC_DECLINE': { status: 'Declined', message: '✗ Card Declined' },
    'DECLINE': { status: 'Declined', message: '✗ Card Declined' },
    'DECLINED': { status: 'Declined', message: '✗ Card Declined' },
    'TRANSACTION_NOT_ALLOWED': { status: 'Declined', message: '✗ Transaction Not Allowed' },
    'PAYMENT_DECLINED': { status: 'Declined', message: '✗ Payment Declined' },
    'AUTHORIZATION_DECLINED': { status: 'Declined', message: '✗ Authorization Declined' },
    
    // Do Not Honor
    'DO_NOT_HONOR': { status: 'Declined', message: '✗ Do Not Honor' },
    'DO_NOT_HONOUR': { status: 'Declined', message: '✗ Do Not Honor' },
    'HONOR_DECLINED': { status: 'Declined', message: '✗ Do Not Honor' },
    
    // Lost/Stolen Card
    'LOST_OR_STOLEN_CARD': { status: 'Declined', message: '✗ Lost/Stolen Card' },
    'LOST_CARD': { status: 'Declined', message: '✗ Lost Card' },
    'STOLEN_CARD': { status: 'Declined', message: '✗ Stolen Card' },
    'PICK_UP_CARD': { status: 'Declined', message: '✗ Pick Up Card (Stolen)' },
    'RESTRICTED_CARD': { status: 'Declined', message: '✗ Restricted Card' },
    
    // Expired Card
    'EXPIRED_CARD': { status: 'Declined', message: '✗ Expired Card' },
    'CARD_EXPIRED': { status: 'Declined', message: '✗ Card Expired' },
    'EXPIRY_DATE_INVALID': { status: 'Declined', message: '✗ Expiry Date Invalid' },
    'INVALID_EXPIRY_DATE': { status: 'Declined', message: '✗ Invalid Expiry Date' },
    'EXPIRATION_DATE_INVALID': { status: 'Declined', message: '✗ Expiration Invalid' },
    
    // Invalid Card
    'INVALID_NUMBER': { status: 'Declined', message: '✗ Invalid Card Number' },
    'INVALID_CARD': { status: 'Declined', message: '✗ Invalid Card' },
    'INVALID_CARD_NUMBER': { status: 'Declined', message: '✗ Invalid Card Number' },
    'CARD_NUMBER_INVALID': { status: 'Declined', message: '✗ Card Number Invalid' },
    'INVALID_ACCOUNT': { status: 'Declined', message: '✗ Invalid Account' },
    'ACCOUNT_INVALID': { status: 'Declined', message: '✗ Invalid Account' },
    
    // Card Type Issues
    'INVALID_CARD_TYPE': { status: 'Declined', message: '✗ Invalid Card Type' },
    'CARD_NOT_SUPPORTED': { status: 'Declined', message: '✗ Card Not Supported' },
    'CARD_TYPE_NOT_ACCEPTED': { status: 'Declined', message: '✗ Card Type Not Accepted' },
    'UNSUPPORTED_CARD': { status: 'Declined', message: '✗ Unsupported Card' },
    
    // Fraud/Security
    'FRAUD': { status: 'Declined', message: '✗ Fraud Detected' },
    'FRAUD_DETECTED': { status: 'Declined', message: '✗ Fraud Detected' },
    'SUSPECTED_FRAUD': { status: 'Declined', message: '✗ Suspected Fraud' },
    'SECURITY_VIOLATION': { status: 'Declined', message: '✗ Security Violation' },
    'FRAUDULENT': { status: 'Declined', message: '✗ Fraudulent Transaction' },
    
    // Processing Errors
    'PROCESSING_ERROR': { status: 'Declined', message: '✗ Processing Error' },
    'PROCESSOR_DECLINED': { status: 'Declined', message: '✗ Processor Declined' },
    'ISSUER_DECLINED': { status: 'Declined', message: '✗ Issuer Declined' },
    'BANK_DECLINED': { status: 'Declined', message: '✗ Bank Declined' },
    
    // Contact Issuer
    'CALL_ISSUER': { status: 'Declined', message: '✗ Call Issuer' },
    'CONTACT_BANK': { status: 'Declined', message: '✗ Contact Bank' },
    'REFER_TO_ISSUER': { status: 'Declined', message: '✗ Refer to Issuer' },
    
    // Amount Issues
    'INVALID_AMOUNT': { status: 'Declined', message: '✗ Invalid Amount' },
    'AMOUNT_TOO_LARGE': { status: 'Declined', message: '✗ Amount Too Large' },
    'AMOUNT_TOO_SMALL': { status: 'Declined', message: '✗ Amount Too Small' },
    'EXCEEDS_LIMIT': { status: 'Declined', message: '✗ Exceeds Limit' },
    'LIMIT_EXCEEDED': { status: 'Declined', message: '✗ Limit Exceeded' },
    
    // Retry/Temporary Issues
    'TRY_AGAIN_LATER': { status: 'Declined', message: '✗ Try Again Later' },
    'TEMPORARY_DECLINE': { status: 'Declined', message: '✗ Temporary Decline' },
    'REENTER_TRANSACTION': { status: 'Declined', message: '✗ Re-enter Transaction' },
    
    // ==================== 3DS/AUTHENTICATION ====================
    'CompletePaymentChallenge': { status: '3DS', message: '3D Secure Required' },
    'stripeAuthentications': { status: '3DS', message: 'Stripe 3DS Required' },
    'ACTION_REQUIRED': { status: '3DS', message: 'Authentication Required' },
    'AUTHENTICATION_REQUIRED': { status: '3DS', message: '3D Secure Required' },
    'AUTHENTICATION_FAILED': { status: 'Declined', message: '✗ 3DS Authentication Failed' },
    'THREE_D_SECURE_REQUIRED': { status: '3DS', message: '3D Secure Required' },
    'SCA_REQUIRED': { status: '3DS', message: 'SCA Required' },
    
    // ==================== SITE/SYSTEM ERRORS ====================
    'RATE_LIMITED': { status: 'Error', message: 'Rate Limited - Retry' },
    'THROTTLED': { status: 'Error', message: 'Throttled - Wait & Retry' },
    'SITE_ERROR': { status: 'Error', message: 'Site Error' },
    'NETWORK_ERROR': { status: 'Error', message: 'Network Error' },
    'TIMEOUT': { status: 'Error', message: 'Request Timeout' },
    'CONNECTION_ERROR': { status: 'Error', message: 'Connection Error' },
    'SERVER_ERROR': { status: 'Error', message: 'Server Error' },
    'INTERNAL_ERROR': { status: 'Error', message: 'Internal Error' },
    
    // ==================== CHECKOUT/PRODUCT ERRORS ====================
    'DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE': { status: 'Error', message: 'Cannot Ship to Address' },
    'PRODUCT_NOT_AVAILABLE': { status: 'Error', message: 'Product Out of Stock' },
    'CHECKOUT_EXPIRED': { status: 'Error', message: 'Checkout Expired' },
    'INVALID_CHECKOUT': { status: 'Error', message: 'Invalid Checkout' },
    'STOCK': { status: 'Error', message: 'Out of Stock' },
    'OUT_OF_STOCK': { status: 'Error', message: 'Out of Stock' },
    'UNAVAILABLE': { status: 'Error', message: 'Product Unavailable' },
    
    // ==================== TAX/PRICE ERRORS ====================
    'TAX_NEW_TAX_MUST_BE_ACCEPTED': { status: 'Error', message: 'Tax Changed - Retry' },
    'PAYMENTS_UNACCEPTABLE_PAYMENT_AMOUNT': { status: 'Error', message: 'Price Changed - Retry' },
    'PRICE_CHANGED': { status: 'Error', message: 'Price Changed - Retry' },
    'TAX_CALCULATION_FAILED': { status: 'Error', message: 'Tax Calculation Failed' }
};

/**
 * Enhanced keyword detection for better categorization
 */
export const KEYWORD_PATTERNS = {
    // Live indicators (card is valid but has issues)
    live: [
        'cvv', 'cvc', 'security code', 'incorrect_cvc', 'incorrect_cvv',
        'zip', 'postal', 'avs', 'address', 'incorrect_zip',
        'insufficient', 'balance', 'funds', 'exceeds balance',
        'number mismatch', 'incorrect_number'
    ],
    
    // Charged/Success indicators
    charged: [
        'success', 'approved', 'confirmed', 'complete', 'charged',
        'thank you', 'thank_you', 'order confirmed', 'payment successful',
        'transaction approved', 'ProcessedReceipt', 'charge succeeded'
    ],
    
    // Declined indicators
    declined: [
        'declined', 'reject', 'deny', 'denied', 'do not honor',
        'lost', 'stolen', 'pick up', 'restricted',
        'expired', 'invalid', 'fraud', 'security violation',
        'call issuer', 'contact bank', 'processor declined',
        'limit exceeded', 'not allowed', 'unsupported'
    ],
    
    // Error indicators
    error: [
        'error', 'failed', 'timeout', 'rate limit', 'throttle',
        'session', 'captcha', 'stock', 'unavailable', 'expired checkout'
    ],
    
    // 3DS indicators
    '3ds': [
        '3d secure', '3ds', 'authentication', 'sca', 'challenge',
        'CompletePaymentChallenge', 'stripeAuthentications'
    ]
};

export default RESPONSE_CODES;
