/**
 * Addresses Database - Multiple Countries
 * Based on PHP site.php patterns
 */

// Country-specific addresses
const addressesByCountry = {
    US: [
        { street: "1234 Sunset Blvd", city: "Los Angeles", state: "CA", postcode: "90001", country: "US", currency: "USD", phone: "+12135551234" },
        { street: "567 Madison Ave", city: "New York", state: "NY", postcode: "10001", country: "US", currency: "USD", phone: "+12125551234" },
        { street: "890 Michigan Ave", city: "Chicago", state: "IL", postcode: "60601", country: "US", currency: "USD", phone: "+13125551234" },
        { street: "1234 Main St", city: "Houston", state: "TX", postcode: "77001", country: "US", currency: "USD", phone: "+17135551234" },
        { street: "567 Central Ave", city: "Phoenix", state: "AZ", postcode: "85001", country: "US", currency: "USD", phone: "+16025551234" },
        { street: "890 Market St", city: "Philadelphia", state: "PA", postcode: "19101", country: "US", currency: "USD", phone: "+12155551234" },
        { street: "1234 Commerce St", city: "San Antonio", state: "TX", postcode: "78201", country: "US", currency: "USD", phone: "+12105551234" },
        { street: "567 Broadway", city: "San Diego", state: "CA", postcode: "92101", country: "US", currency: "USD", phone: "+16195551234" },
        { street: "890 Elm St", city: "Dallas", state: "TX", postcode: "75201", country: "US", currency: "USD", phone: "+12145551234" },
        { street: "1234 Santa Clara St", city: "San Jose", state: "CA", postcode: "95101", country: "US", currency: "USD", phone: "+14085551234" }
    ],
    UK: [
        { street: "10 Downing Street", city: "London", state: "", postcode: "SW1A 2AA", country: "GB", currency: "GBP", phone: "+442071234567" },
        { street: "221B Baker Street", city: "London", state: "", postcode: "NW1 6XE", country: "GB", currency: "GBP", phone: "+442079876543" },
        { street: "1 Oxford Street", city: "London", state: "", postcode: "W1D 2DW", country: "GB", currency: "GBP", phone: "+442075551234" },
        { street: "50 Piccadilly", city: "Manchester", state: "", postcode: "M1 2AP", country: "GB", currency: "GBP", phone: "+441611234567" }
    ],
    GB: [
        { street: "10 Downing Street", city: "London", state: "", postcode: "SW1A 2AA", country: "GB", currency: "GBP", phone: "+442071234567" },
        { street: "221B Baker Street", city: "London", state: "", postcode: "NW1 6XE", country: "GB", currency: "GBP", phone: "+442079876543" }
    ],
    CA: [
        { street: "123 Queen Street West", city: "Toronto", state: "ON", postcode: "M5H 2N2", country: "CA", currency: "CAD", phone: "+14165551234" },
        { street: "456 Robson Street", city: "Vancouver", state: "BC", postcode: "V6B 2A8", country: "CA", currency: "CAD", phone: "+16045551234" },
        { street: "789 St Catherine Street", city: "Montreal", state: "QC", postcode: "H3B 1A2", country: "CA", currency: "CAD", phone: "+15145551234" }
    ],
    AU: [
        { street: "123 George Street", city: "Sydney", state: "NSW", postcode: "2000", country: "AU", currency: "AUD", phone: "+61291234567" },
        { street: "456 Bourke Street", city: "Melbourne", state: "VIC", postcode: "3000", country: "AU", currency: "AUD", phone: "+61391234567" },
        { street: "789 Queen Street", city: "Brisbane", state: "QLD", postcode: "4000", country: "AU", currency: "AUD", phone: "+61731234567" }
    ],
    IN: [
        { street: "123 MG Road", city: "Mumbai", state: "MH", postcode: "400001", country: "IN", currency: "INR", phone: "+919876543210" },
        { street: "456 Connaught Place", city: "New Delhi", state: "DL", postcode: "110001", country: "IN", currency: "INR", phone: "+919123456789" },
        { street: "789 Brigade Road", city: "Bangalore", state: "KA", postcode: "560001", country: "IN", currency: "INR", phone: "+918765432109" }
    ],
    FR: [
        { street: "1 Rue de Rivoli", city: "Paris", state: "", postcode: "75001", country: "FR", currency: "EUR", phone: "+33142123456" },
        { street: "25 Avenue des Champs-Élysées", city: "Paris", state: "", postcode: "75008", country: "FR", currency: "EUR", phone: "+33145678901" }
    ],
    DE: [
        { street: "1 Unter den Linden", city: "Berlin", state: "", postcode: "10117", country: "DE", currency: "EUR", phone: "+493012345678" },
        { street: "50 Königsallee", city: "Düsseldorf", state: "", postcode: "40212", country: "DE", currency: "EUR", phone: "+492111234567" }
    ],
    BR: [
        { street: "Av Paulista 1000", city: "São Paulo", state: "SP", postcode: "01310-100", country: "BR", currency: "BRL", phone: "+5511987654321" },
        { street: "Av Atlântica 500", city: "Rio de Janeiro", state: "RJ", postcode: "22010-000", country: "BR", currency: "BRL", phone: "+5521987654321" }
    ],
    VN: [
        { street: "123 Nguyen Hue", city: "Ho Chi Minh City", state: "", postcode: "700000", country: "VN", currency: "VND", phone: "+84901234567" },
        { street: "456 Hang Bai", city: "Hanoi", state: "", postcode: "100000", country: "VN", currency: "VND", phone: "+84912345678" }
    ],
    NZ: [
        { street: "1 Queen Street", city: "Auckland", state: "", postcode: "1010", country: "NZ", currency: "NZD", phone: "+6491234567" },
        { street: "100 Lambton Quay", city: "Wellington", state: "", postcode: "6011", country: "NZ", currency: "NZD", phone: "+6441234567" }
    ],
    SG: [
        { street: "1 Orchard Road", city: "Singapore", state: "", postcode: "238823", country: "SG", currency: "SGD", phone: "+6561234567" }
    ],
    AE: [
        { street: "1 Sheikh Zayed Road", city: "Dubai", state: "DU", postcode: "00000", country: "AE", currency: "AED", phone: "+971501234567" }
    ],
    JP: [
        { street: "1-1 Marunouchi", city: "Tokyo", state: "", postcode: "100-0005", country: "JP", currency: "JPY", phone: "+81312345678" },
        { street: "1 Shinsaibashi", city: "Osaka", state: "", postcode: "542-0085", country: "JP", currency: "JPY", phone: "+81612345678" }
    ]
};

// Legacy format for backwards compatibility
export const addresses = [
    { city: "Los Angeles", state: "CA", zip: "90001", address: "1234 Sunset Blvd" },
    { city: "New York", state: "NY", zip: "10001", address: "567 Madison Ave" },
    { city: "Chicago", state: "IL", zip: "60601", address: "890 Michigan Ave" },
    { city: "Houston", state: "TX", zip: "77001", address: "1234 Main St" },
    { city: "Phoenix", state: "AZ", zip: "85001", address: "567 Central Ave" },
    { city: "Philadelphia", state: "PA", zip: "19101", address: "890 Market St" },
    { city: "San Antonio", state: "TX", zip: "78201", address: "1234 Commerce St" },
    { city: "San Diego", state: "CA", zip: "92101", address: "567 Broadway" },
    { city: "Dallas", state: "TX", zip: "75201", address: "890 Elm St" },
    { city: "San Jose", state: "CA", zip: "95101", address: "1234 Santa Clara St" },
    { city: "Austin", state: "TX", zip: "78701", address: "567 Congress Ave" },
    { city: "Jacksonville", state: "FL", zip: "32099", address: "890 Bay St" },
    { city: "Fort Worth", state: "TX", zip: "76101", address: "1234 Main St" },
    { city: "Columbus", state: "OH", zip: "43085", address: "567 High St" },
    { city: "Charlotte", state: "NC", zip: "28201", address: "890 Tryon St" },
    { city: "San Francisco", state: "CA", zip: "94102", address: "1234 Market St" },
    { city: "Indianapolis", state: "IN", zip: "46201", address: "567 Meridian St" },
    { city: "Seattle", state: "WA", zip: "98101", address: "890 Pike St" },
    { city: "Denver", state: "CO", zip: "80201", address: "1234 16th St" },
    { city: "Washington", state: "DC", zip: "20001", address: "567 Pennsylvania Ave" },
    { city: "Boston", state: "MA", zip: "02101", address: "890 Boylston St" },
    { city: "El Paso", state: "TX", zip: "79901", address: "1234 Mesa St" },
    { city: "Nashville", state: "TN", zip: "37201", address: "567 Broadway" },
    { city: "Detroit", state: "MI", zip: "48201", address: "890 Woodward Ave" },
    { city: "Oklahoma City", state: "OK", zip: "73101", address: "1234 Robinson Ave" },
    { city: "Portland", state: "OR", zip: "97201", address: "567 Burnside St" },
    { city: "Las Vegas", state: "NV", zip: "89101", address: "890 Fremont St" },
    { city: "Memphis", state: "TN", zip: "38101", address: "1234 Beale St" },
    { city: "Louisville", state: "KY", zip: "40201", address: "567 Main St" },
    { city: "Baltimore", state: "MD", zip: "21201", address: "890 Pratt St" },
    { city: "Milwaukee", state: "WI", zip: "53201", address: "1234 Wisconsin Ave" },
    { city: "Albuquerque", state: "NM", zip: "87101", address: "567 Central Ave" },
    { city: "Tucson", state: "AZ", zip: "85701", address: "890 Congress St" },
    { city: "Fresno", state: "CA", zip: "93701", address: "1234 Fulton St" },
    { city: "Sacramento", state: "CA", zip: "95814", address: "567 K St" },
    { city: "Kansas City", state: "MO", zip: "64101", address: "890 Main St" },
    { city: "Mesa", state: "AZ", zip: "85201", address: "1234 Main St" },
    { city: "Atlanta", state: "GA", zip: "30301", address: "567 Peachtree St" },
    { city: "Miami", state: "FL", zip: "33101", address: "890 Biscayne Blvd" }
];

/**
 * Get a random address (US default, normalized format)
 */
export function getRandomAddress() {
    const usAddresses = addressesByCountry.US;
    return usAddresses[Math.floor(Math.random() * usAddresses.length)];
}

/**
 * Get address by country code
 */
export function getAddressByCountry(countryCode) {
    const code = (countryCode || 'US').toUpperCase();
    
    // Map common variations
    const countryMap = {
        'UK': 'GB',
        'USA': 'US',
        'CANADA': 'CA',
        'AUSTRALIA': 'AU',
        'INDIA': 'IN',
        'FRANCE': 'FR',
        'GERMANY': 'DE',
        'BRAZIL': 'BR',
        'VIETNAM': 'VN',
        'JAPAN': 'JP',
        'SINGAPORE': 'SG',
        'UAE': 'AE'
    };
    
    const normalizedCode = countryMap[code] || code;
    const countryAddresses = addressesByCountry[normalizedCode] || addressesByCountry.US;
    
    return countryAddresses[Math.floor(Math.random() * countryAddresses.length)];
}

/**
 * Get address by state
 */
export function getAddressByState(state) {
    const usAddresses = addressesByCountry.US;
    const filtered = usAddresses.filter(a => a.state.toLowerCase() === state.toLowerCase());
    if (filtered.length === 0) return getRandomAddress();
    return filtered[Math.floor(Math.random() * filtered.length)];
}

/**
 * Get all states
 */
export function getStates() {
    return [...new Set(addressesByCountry.US.map(a => a.state))];
}

/**
 * Get all countries
 */
export function getCountries() {
    return Object.keys(addressesByCountry);
}

export { addressesByCountry };
export default addresses;
