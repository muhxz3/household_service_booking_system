# Payment Simulation System

This document explains how the payment simulation system works in the My Eazy Day household service booking platform.

## Overview

The payment simulation system allows testing of different payment scenarios without processing real transactions. This is essential for development, testing, and demonstration purposes.

## How It Works

When a customer selects "Online Payment" during booking, they are redirected to the payment simulation page instead of a real payment gateway.

## Available Test Scenarios

### 1. ✅ Successful Payment
- **Description**: Payment completes successfully
- **Database Impact**:
  - Payment status: `completed`
  - Booking status: `confirmed`
- **User Experience**: Redirected to bookings page with success message

### 2. ❌ Payment Failed
- **Description**: Simulates insufficient funds or card declined
- **Database Impact**:
  - Payment status: `failed`
  - Booking status: unchanged (pending)
- **User Experience**: Error message, can retry or choose cash payment

### 3. ⏱️ Payment Timeout
- **Description**: Simulates network issues or gateway timeout
- **Database Impact**: No changes (payment stays pending)
- **User Experience**: Warning message, payment remains pending

### 4. 🔄 Processing
- **Description**: Payment initiated but still processing
- **Database Impact**:
  - Payment status: `processing`
  - Booking status: unchanged
- **User Experience**: Info message, payment status shows as processing

## File Structure

```
payment_simulation.html      # Simulation UI template
payment_simulator.py         # Simulation logic and utilities
app.py                       # Updated with simulation routes
```

## Routes Added

- `/payment_simulation/<booking_id>` - Displays simulation page
- `/process_payment_simulation` - Processes simulation results

## Test Data

The simulation page comes pre-filled with test payment details:
- **Card Number**: 4111111111111111 (any 16-digit number works)
- **Expiry**: 12/25
- **CVV**: 123
- **Name**: Test User

## Usage Instructions

1. **Make a booking** with "Online Payment" selected
2. **Choose a scenario** from the radio buttons
3. **Click "Process Test Payment"**
4. **Observe the result** in the flash message and booking status

## Benefits

- **Safe Testing**: No real money involved
- **Error Simulation**: Test failure scenarios
- **Workflow Validation**: Ensure proper status updates
- **User Experience Testing**: Verify messaging and redirects

## Future Integration

When ready for production, replace the simulation routes with real payment gateway integration (Razorpay, Stripe, etc.) while keeping the same database structure and user flow.

## Configuration

The system currently runs in simulation mode by default. To enable real payments in the future, modify the `is_simulation_mode()` function in `payment_simulator.py` to check environment variables or configuration settings.