# Payment Simulation Utilities
# This module provides simulation functionality for testing payment scenarios

import time
import random

class PaymentSimulator:
    """Handles payment simulation scenarios for testing purposes"""
    
    @staticmethod
    def simulate_payment_scenario(scenario, booking_id, amount):
        """
        Simulates different payment outcomes
        
        Args:
            scenario (str): 'success', 'failure', 'timeout', 'processing'
            booking_id (int): The booking ID
            amount (float): Payment amount
            
        Returns:
            dict: Simulation result with status and message
        """
        
        if scenario == 'success':
            # Simulate successful payment processing
            time.sleep(0.5)  # Brief delay to simulate processing
            transaction_id = f"SIM{random.randint(100000, 999999)}"
            return {
                'status': 'completed',
                'message': 'Payment processed successfully',
                'transaction_id': transaction_id,
                'amount': amount
            }
            
        elif scenario == 'failure':
            # Simulate payment failure
            time.sleep(0.3)
            return {
                'status': 'failed',
                'message': 'Payment declined - insufficient funds',
                'transaction_id': None,
                'amount': amount
            }
            
        elif scenario == 'timeout':
            # Simulate gateway timeout
            time.sleep(2)  # Longer delay
            return {
                'status': 'timeout',
                'message': 'Payment gateway timeout - please retry',
                'transaction_id': None,
                'amount': amount
            }
            
        elif scenario == 'processing':
            # Payment initiated but still processing
            time.sleep(0.2)
            return {
                'status': 'processing',
                'message': 'Payment is being processed',
                'transaction_id': f"PENDING{random.randint(100000, 999999)}",
                'amount': amount
            }
            
        else:
            return {
                'status': 'error',
                'message': 'Invalid simulation scenario',
                'transaction_id': None,
                'amount': amount
            }

def get_simulation_scenarios():
    """
    Returns available simulation scenarios for UI display
    
    Returns:
        list: List of scenario dictionaries with id, name, description
    """
    return [
        {
            'id': 'success',
            'name': 'Successful Payment',
            'description': 'Payment completes successfully',
            'icon': '✅'
        },
        {
            'id': 'failure',
            'name': 'Payment Failed',
            'description': 'Simulates insufficient funds or card declined',
            'icon': '❌'
        },
        {
            'id': 'timeout',
            'name': 'Payment Timeout',
            'description': 'Simulates network issues or gateway timeout',
            'icon': '⏱️'
        },
        {
            'id': 'processing',
            'name': 'Processing',
            'description': 'Payment stays in processing state',
            'icon': '🔄'
        }
    ]

def is_simulation_mode():
    """
    Check if the application is running in simulation mode
    
    Returns:
        bool: True if simulation mode is enabled
    """
    # For now, always return True since this is a simulation module
    # In production, this could check an environment variable or config setting
    return True