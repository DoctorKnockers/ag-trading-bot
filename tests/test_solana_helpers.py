"""Tests for Solana helper functions."""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from utils.solana_helpers import validate_spl_mint, is_valid_solana_address


class TestSolanaHelpers:
    """Test Solana utility functions."""
    
    def test_is_valid_solana_address_valid(self):
        """Test valid Solana address format."""
        # USDC mint (known valid)
        valid_address = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        assert is_valid_solana_address(valid_address) is True
    
    def test_is_valid_solana_address_invalid(self):
        """Test invalid address formats."""
        # Too short
        assert is_valid_solana_address("123") is False
        
        # Invalid characters
        assert is_valid_solana_address("0123456789012345678901234567890123456789") is False
        
        # Empty string
        assert is_valid_solana_address("") is False
    
    @pytest.mark.asyncio
    async def test_validate_spl_mint_valid(self):
        """Test validation of valid SPL mint."""
        mock_account_info = {
            "owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
            "data": {
                "parsed": {
                    "type": "mint",
                    "info": {
                        "supply": "1000000000",
                        "decimals": 9,
                        "mintAuthority": None,
                        "freezeAuthority": None
                    }
                }
            }
        }
        
        with patch('utils.solana_helpers.SolanaRPCClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get_account_info.return_value = mock_account_info
            
            is_valid, status, mint_info = await validate_spl_mint("ValidMint123")
            
            assert is_valid is True
            assert status == "VALID_SPL_MINT"
            assert mint_info["supply"] == "1000000000"
            assert mint_info["decimals"] == 9
    
    @pytest.mark.asyncio
    async def test_validate_spl_mint_infinite_mint(self):
        """Test rejection of mint with mintAuthority."""
        mock_account_info = {
            "owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
            "data": {
                "parsed": {
                    "type": "mint",
                    "info": {
                        "supply": "1000000000",
                        "decimals": 9,
                        "mintAuthority": "BadActor123",  # Has mint authority!
                        "freezeAuthority": None
                    }
                }
            }
        }
        
        with patch('utils.solana_helpers.SolanaRPCClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get_account_info.return_value = mock_account_info
            
            is_valid, status, mint_info = await validate_spl_mint("BadMint123")
            
            assert is_valid is False
            assert status == "INFINITE_MINT"
            assert mint_info["mintAuthority"] == "BadActor123"
    
    @pytest.mark.asyncio
    async def test_validate_spl_mint_freeze_backdoor(self):
        """Test rejection of mint with freezeAuthority."""
        mock_account_info = {
            "owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
            "data": {
                "parsed": {
                    "type": "mint",
                    "info": {
                        "supply": "1000000000",
                        "decimals": 9,
                        "mintAuthority": None,
                        "freezeAuthority": "Freezer123"  # Has freeze authority!
                    }
                }
            }
        }
        
        with patch('utils.solana_helpers.SolanaRPCClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get_account_info.return_value = mock_account_info
            
            is_valid, status, mint_info = await validate_spl_mint("FreezeMint123")
            
            assert is_valid is False
            assert status == "FREEZE_BACKDOOR"
            assert mint_info["freezeAuthority"] == "Freezer123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
