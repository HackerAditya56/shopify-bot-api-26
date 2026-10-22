/**
 * Shopify GraphQL Queries
 * For checkout proposal, submission, and polling
 */

// Proposal query - No shipping (digital products)
export const proposalNone = `
mutation Proposal($token: String!, $billingAddress: MailingAddressInput!, $paymentMethod: PaymentMethodInput!, $sessionInput: SessionInput!) {
  checkoutComplete(
    token: $token
    billingAddress: $billingAddress
    paymentMethod: $paymentMethod
    sessionInput: $sessionInput
  ) {
    ... on SubmitAlreadyAccepted {
      receipt {
        id
        ...ReceiptDetails
      }
    }
    ... on SubmitFailed {
      errors {
        code
        localizedMessage
      }
    }
    ... on SubmitThrottled {
      pollAfter
    }
    ... on SubmitSuccess {
      receipt {
        ...ReceiptDetails
      }
    }
    ... on SubmitPending {
      queueToken
    }
    ... on ActionRequired {
      action {
        ... on CompletePaymentChallenge {
          offsiteRedirect
          url
        }
      }
    }
  }
}

fragment ReceiptDetails on Receipt {
  id
  token
  processedAt
  orderStatusUrl
  purchasingEntity
}
`;

// Proposal query - With shipping
export const proposalShipping = `
mutation Proposal($token: String!, $shippingAddress: MailingAddressInput!, $billingAddress: MailingAddressInput!, $paymentMethod: PaymentMethodInput!, $sessionInput: SessionInput!) {
  checkoutComplete(
    token: $token
    shippingAddress: $shippingAddress
    billingAddress: $billingAddress
    paymentMethod: $paymentMethod
    sessionInput: $sessionInput
  ) {
    ... on SubmitAlreadyAccepted {
      receipt {
        id
        ...ReceiptDetails
      }
    }
    ... on SubmitFailed {
      errors {
        code
        localizedMessage
      }
    }
    ... on SubmitThrottled {
      pollAfter
    }
    ... on SubmitSuccess {
      receipt {
        ...ReceiptDetails
      }
    }
    ... on SubmitPending {
      queueToken
    }
    ... on ActionRequired {
      action {
        ... on CompletePaymentChallenge {
          offsiteRedirect
          url
        }
      }
    }
  }
}

fragment ReceiptDetails on Receipt {
  id
  token
  processedAt
  orderStatusUrl
  purchasingEntity
}
`;

// Submit for completion query
export const submitForCompletion = `
mutation SubmitForCompletion($token: String!) {
  checkoutSubmitForCompletion(token: $token) {
    ... on SubmitAlreadyAccepted {
      receipt {
        id
        ...ReceiptDetails
      }
    }
    ... on SubmitFailed {
      errors {
        code
        localizedMessage
      }
    }
    ... on SubmitThrottled {
      pollAfter
    }
    ... on SubmitSuccess {
      receipt {
        ...ReceiptDetails
      }
    }
    ... on SubmitPending {
      queueToken
    }
    ... on ActionRequired {
      action {
        ... on CompletePaymentChallenge {
          offsiteRedirect
          url
        }
      }
    }
  }
}

fragment ReceiptDetails on Receipt {
  id
  token
  processedAt
  orderStatusUrl
  purchasingEntity
}
`;

// Submit for completion with payment (alternative)
export const submitForCompletionWithPayment = `
mutation SubmitForCompletion($token: String!, $paymentToken: String!, $totalAmount: MoneyInput!) {
  checkoutCompleteWithTokenizedPaymentV3(
    token: $token
    payment: {
      paymentAmount: $totalAmount
      idempotencyKey: $token
      billingAddress: {
        firstName: "."
        lastName: "."
        address1: "."
        city: "."
        province: "."
        country: "."
        zip: "."
      }
      paymentData: $paymentToken
      type: "shopify_pay"
    }
  ) {
    checkout {
      id
      webUrl
    }
    checkoutUserErrors {
      code
      field
      message
    }
    payment {
      id
      errorMessage
      ready
    }
  }
}
`;

// Poll for receipt query
export const pollForReceipt = `
mutation PollForReceipt($token: String!, $queueToken: String!) {
  poll(token: $token, queueToken: $queueToken) {
    ... on SubmitAlreadyAccepted {
      receipt {
        id
        ...ReceiptDetails
      }
    }
    ... on SubmitFailed {
      errors {
        code
        localizedMessage
      }
    }
    ... on SubmitThrottled {
      pollAfter
    }
    ... on SubmitSuccess {
      receipt {
        ...ReceiptDetails
      }
    }
    ... on SubmitPending {
      queueToken
    }
    ... on ActionRequired {
      action {
        ... on CompletePaymentChallenge {
          offsiteRedirect
          url
        }
      }
    }
  }
}

fragment ReceiptDetails on Receipt {
  id
  token
  processedAt
  orderStatusUrl
  purchasingEntity
}
`;

// Storefront cart creation
export const createCart = `
mutation createCart($input: CartInput!) {
  cartCreate(input: $input) {
    cart {
      id
      checkoutUrl
      lines(first: 10) {
        edges {
          node {
            id
            quantity
            merchandise {
              ... on ProductVariant {
                id
                title
                price {
                  amount
                  currencyCode
                }
              }
            }
          }
        }
      }
      cost {
        totalAmount {
          amount
          currencyCode
        }
        subtotalAmount {
          amount
          currencyCode
        }
      }
    }
    userErrors {
      code
      field
      message
    }
  }
}
`;

// Get product by handle
export const getProductByHandle = `
query getProductByHandle($handle: String!) {
  product(handle: $handle) {
    id
    title
    description
    handle
    availableForSale
    priceRange {
      minVariantPrice {
        amount
        currencyCode
      }
      maxVariantPrice {
        amount
        currencyCode
      }
    }
    variants(first: 100) {
      edges {
        node {
          id
          title
          price {
            amount
            currencyCode
          }
          availableForSale
          quantityAvailable
        }
      }
    }
  }
}
`;

// Get minimum price product details
export const getMinimumPriceProduct = `
query getProducts($first: Int!) {
  products(first: $first, sortKey: PRICE) {
    edges {
      node {
        id
        title
        handle
        availableForSale
        variants(first: 1) {
          edges {
            node {
              id
              price {
                amount
                currencyCode
              }
            }
          }
        }
      }
    }
  }
}
`;

export default {
    proposalNone,
    proposalShipping,
    submitForCompletion,
    submitForCompletionWithPayment,
    pollForReceipt,
    createCart,
    getProductByHandle,
    getMinimumPriceProduct
};
