"""
Rich Console Dashboard for AG Trading Bot
Real-time monitoring with visual feedback for manual traders
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
import asyncpg

from config import settings

logger = logging.getLogger(__name__)


class TradingDashboard:
    """
    Rich console dashboard for real-time trading monitoring.
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        """
        Initialize dashboard.
        
        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool
        self.console = Console()
        self.layout = Layout()
        
        # Dashboard data
        self.signals = []
        self.performance = {}
        self.evolution_status = {}
        self.validation_queue = []
        
        # Setup layout
        self.setup_layout()
        
        # Update interval
        self.update_interval = 2  # seconds
    
    def setup_layout(self):
        """Setup dashboard layout structure."""
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )
        
        # Split main area
        self.layout["main"].split_row(
            Layout(name="signals", ratio=2),
            Layout(name="stats", ratio=1)
        )
        
        # Split stats area
        self.layout["stats"].split_column(
            Layout(name="performance"),
            Layout(name="evolution")
        )
    
    def create_header(self) -> Panel:
        """Create header panel."""
        header_text = Text()
        header_text.append("🎯 AG Trading Bot Dashboard", style="bold cyan")
        header_text.append(" | ", style="dim")
        header_text.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style="yellow")
        
        return Panel(header_text, style="cyan", box_type="double")
    
    def create_signals_table(self) -> Table:
        """Create signals table."""
        table = Table(title="📡 Live Trading Signals", expand=True)
        
        # Add columns
        table.add_column("Time", style="dim", width=8)
        table.add_column("Token", style="cyan", width=12)
        table.add_column("Signal", style="bold", width=8)
        table.add_column("Confidence", justify="right", width=10)
        table.add_column("Sentiment", justify="center", width=10)
        table.add_column("Validation", justify="center", width=10)
        table.add_column("Smart $", justify="right", width=8)
        
        # Add recent signals (last 15)
        for signal in self.signals[-15:]:
            # Format signal type with color
            if signal['signal'] == 'BUY':
                signal_text = Text("🟢 BUY", style="green bold")
            else:
                signal_text = Text("🔴 SKIP", style="red")
            
            # Format confidence with color
            conf = signal['confidence']
            if conf > 0.8:
                conf_text = Text(f"{conf:.1%}", style="green")
            elif conf > 0.6:
                conf_text = Text(f"{conf:.1%}", style="yellow")
            else:
                conf_text = Text(f"{conf:.1%}", style="red")
            
            # Format sentiment
            sentiment = signal.get('sentiment', 0)
            if sentiment > 0.3:
                sent_text = Text(f"🐂 {sentiment:.2f}", style="green")
            elif sentiment < -0.3:
                sent_text = Text(f"🐻 {sentiment:.2f}", style="red")
            else:
                sent_text = Text(f"😐 {sentiment:.2f}", style="yellow")
            
            # Format validation
            validation = signal.get('validation', 'UNKNOWN')
            if validation == 'PASS':
                val_text = Text("✅ PASS", style="green")
            elif validation == 'RISKY':
                val_text = Text("⚠️ RISKY", style="yellow")
            else:
                val_text = Text("❌ FAIL", style="red")
            
            # Add row
            table.add_row(
                signal['time'].strftime("%H:%M:%S"),
                signal['token'][:8] + "...",
                signal_text,
                conf_text,
                sent_text,
                val_text,
                str(signal.get('smart_wallets', 0))
            )
        
        return table
    
    def create_performance_panel(self) -> Panel:
        """Create performance statistics panel."""
        # Create stats text
        stats = Text()
        
        # Win rate
        win_rate = self.performance.get('win_rate', 0)
        stats.append("Win Rate: ", style="dim")
        if win_rate > 0.65:
            stats.append(f"{win_rate:.1%}\n", style="green bold")
        elif win_rate > 0.5:
            stats.append(f"{win_rate:.1%}\n", style="yellow")
        else:
            stats.append(f"{win_rate:.1%}\n", style="red")
        
        # Total signals
        stats.append("Signals (24h): ", style="dim")
        stats.append(f"{self.performance.get('signals_24h', 0)}\n", style="cyan")
        
        # Buy signals
        stats.append("Buy Signals: ", style="dim")
        stats.append(f"{self.performance.get('buy_signals', 0)}\n", style="green")
        
        # Active monitoring
        stats.append("Monitoring: ", style="dim")
        stats.append(f"{self.performance.get('active_monitoring', 0)}\n", style="yellow")
        
        # Sharpe ratio
        sharpe = self.performance.get('sharpe_ratio', 0)
        stats.append("Sharpe: ", style="dim")
        if sharpe > 2:
            stats.append(f"{sharpe:.2f}\n", style="green bold")
        elif sharpe > 1:
            stats.append(f"{sharpe:.2f}\n", style="yellow")
        else:
            stats.append(f"{sharpe:.2f}\n", style="red")
        
        return Panel(stats, title="📊 Performance", border_style="blue")
    
    def create_evolution_panel(self) -> Panel:
        """Create evolution status panel."""
        evo_text = Text()
        
        # Evolution status
        status = self.evolution_status.get('status', 'IDLE')
        evo_text.append("Status: ", style="dim")
        
        if status == 'RUNNING':
            evo_text.append(f"{status}\n", style="yellow blink")
        elif status == 'COMPLETE':
            evo_text.append(f"{status}\n", style="green")
        else:
            evo_text.append(f"{status}\n", style="dim")
        
        # Current generation
        if status == 'RUNNING':
            gen = self.evolution_status.get('generation', 0)
            max_gen = self.evolution_status.get('max_generation', 50)
            evo_text.append(f"Generation: {gen}/{max_gen}\n", style="cyan")
            
            # Best fitness
            best_fitness = self.evolution_status.get('best_fitness', 0)
            evo_text.append(f"Best Fitness: {best_fitness:.3f}\n", style="green")
        
        # Last evolution
        last_evo = self.evolution_status.get('last_evolution', 'Never')
        evo_text.append("Last Run: ", style="dim")
        evo_text.append(f"{last_evo}\n", style="cyan")
        
        # Next scheduled
        next_evo = self.evolution_status.get('next_scheduled', 'Not scheduled')
        evo_text.append("Next: ", style="dim")
        evo_text.append(f"{next_evo}\n", style="yellow")
        
        return Panel(evo_text, title="🧬 Evolution", border_style="magenta")
    
    def create_footer(self) -> Panel:
        """Create footer panel."""
        footer_text = Text()
        
        # Add hotkeys
        footer_text.append("[Q]", style="bold red")
        footer_text.append(" Quit  ", style="dim")
        
        footer_text.append("[R]", style="bold yellow")
        footer_text.append(" Refresh  ", style="dim")
        
        footer_text.append("[E]", style="bold green")
        footer_text.append(" Evolve  ", style="dim")
        
        footer_text.append("[S]", style="bold cyan")
        footer_text.append(" Stats  ", style="dim")
        
        return Panel(footer_text, style="dim")
    
    async def update_data(self):
        """Update dashboard data from database."""
        try:
            async with self.db_pool.acquire() as conn:
                # Get recent signals
                signals_query = """
                    SELECT 
                        s.created_at as time,
                        a.mint as token,
                        s.signal,
                        s.score as confidence,
                        fs.features->>'sentiment_score' as sentiment,
                        fs.features->>'validation_verdict' as validation,
                        fs.features->>'smart_wallet_count' as smart_wallets
                    FROM signals s
                    JOIN acceptance_status a ON s.message_id = a.message_id
                    LEFT JOIN features_snapshot fs ON s.message_id = fs.message_id
                    WHERE s.created_at >= NOW() - INTERVAL '1 hour'
                    ORDER BY s.created_at DESC
                    LIMIT 15
                """
                
                rows = await conn.fetch(signals_query)
                self.signals = []
                for row in rows:
                    self.signals.append({
                        'time': row['time'],
                        'token': row['token'],
                        'signal': row['signal'],
                        'confidence': float(row['confidence'] or 0),
                        'sentiment': float(row['sentiment'] or 0),
                        'validation': row['validation'] or 'UNKNOWN',
                        'smart_wallets': int(row['smart_wallets'] or 0)
                    })
                
                # Get performance stats
                perf_query = """
                    SELECT 
                        COUNT(CASE WHEN signal = 'BUY' AND o.win = true THEN 1 END)::float / 
                            NULLIF(COUNT(CASE WHEN signal = 'BUY' THEN 1 END), 0) as win_rate,
                        COUNT(*) as signals_24h,
                        COUNT(CASE WHEN signal = 'BUY' THEN 1 END) as buy_signals,
                        (SELECT COUNT(*) FROM monitor_state WHERE last_seen_at >= NOW() - INTERVAL '5 minutes') as active_monitoring
                    FROM signals s
                    LEFT JOIN outcomes_24h o ON s.message_id = o.message_id
                    WHERE s.created_at >= NOW() - INTERVAL '24 hours'
                """
                
                perf = await conn.fetchrow(perf_query)
                self.performance = {
                    'win_rate': float(perf['win_rate'] or 0),
                    'signals_24h': perf['signals_24h'],
                    'buy_signals': perf['buy_signals'],
                    'active_monitoring': perf['active_monitoring'],
                    'sharpe_ratio': 1.5  # Would calculate from returns
                }
                
        except Exception as e:
            logger.error(f"Dashboard data update failed: {e}")
    
    def update_display(self):
        """Update dashboard display."""
        # Update layout components
        self.layout["header"].update(self.create_header())
        self.layout["signals"].update(self.create_signals_table())
        self.layout["performance"].update(self.create_performance_panel())
        self.layout["evolution"].update(self.create_evolution_panel())
        self.layout["footer"].update(self.create_footer())
        
        return self.layout
    
    async def run(self):
        """Run dashboard main loop."""
        with Live(self.layout, refresh_per_second=1, console=self.console) as live:
            while True:
                # Update data
                await self.update_data()
                
                # Update display
                live.update(self.update_display())
                
                # Wait
                await asyncio.sleep(self.update_interval)


# Example usage
if __name__ == "__main__":
    async def test():
        # Create DB pool
        db_pool = await asyncpg.create_pool(settings.DATABASE_URL)
        
        try:
            # Create and run dashboard
            dashboard = TradingDashboard(db_pool)
            await dashboard.run()
            
        finally:
            await db_pool.close()
    
    asyncio.run(test())