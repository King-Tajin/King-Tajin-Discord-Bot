import discord
from bot.config import Config


async def check_guild(interaction: discord.Interaction) -> bool:
    if not Config.GUILD_ID:
        return True
    if not interaction.guild or interaction.guild.id != int(Config.GUILD_ID):
        await interaction.response.send_message(
            "This command is not available here.", ephemeral=True
        )
        return False
    return True
