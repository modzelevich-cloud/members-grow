import discord
import requests
import json
import os
import asyncio
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import time
from urllib.parse import urlencode, urlparse, parse_qs
import http.server
import threading
import html

print("🚀 FREE MEMBERS BOT STARTING...")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("👋 Members Grow Bot")

# Load config from environment variables (Railway)
BOT_TOKEN = os.getenv('DISCORD_TOKEN')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
MAIN_SERVER = int(os.getenv('MAIN_SERVER', '1500354491629961256'))

if not all([BOT_TOKEN, CLIENT_ID, CLIENT_SECRET]):
    print("❌ Missing DISCORD_TOKEN, CLIENT_ID, or CLIENT_SECRET.")
    exit(1)

# Determine public URL for OAuth redirect
RAILWAY_PUBLIC_DOMAIN = os.getenv('RAILWAY_PUBLIC_DOMAIN', '')
if RAILWAY_PUBLIC_DOMAIN:
    REDIRECT_BASE = f"https://{RAILWAY_PUBLIC_DOMAIN}"
else:
    REDIRECT_BASE = f"http://localhost:{os.getenv('PORT', '5000')}"

print(f"✅ Config loaded")
print(f"🔑 Token: {BOT_TOKEN[:20]}...")
print(f"🆔 Client ID: {CLIENT_ID}")
print(f"🔒 Secret: {CLIENT_SECRET[:8]}...")
print(f"🏠 Main Server: {MAIN_SERVER}")
print(f"🌐 Redirect URL: {REDIRECT_BASE}/callback")

# Create bot
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=['!', '?'], intents=intents)
bot.remove_command("help")

# Store server join times
server_join_times = {}

@bot.event
async def on_ready():
    print(f'🎯 Bot is ready: {bot.user}')
    print(f'📋 Loaded commands: {[command.name for command in bot.commands]}')
    
    # Initialize server join times
    for guild in bot.guilds:
        if guild.id != MAIN_SERVER:
            server_join_times[guild.id] = datetime.now()
            print(f"📝 Tracking server: {guild.name} ({guild.id})")
    
    check_server_ages.start()

@tasks.loop(hours=24)
async def check_server_ages():
    """Check servers and leave if they're older than 14 days (except main server)"""
    print("🔍 Checking server ages...")
    
    for guild in bot.guilds:
        if guild.id == MAIN_SERVER:
            continue
        
        guild_id = guild.id
        guild_name = guild.name
        guild_age = None
        
        if guild_id in server_join_times:
            join_time = server_join_times[guild_id]
            guild_age = datetime.now() - join_time
        else:
            server_join_times[guild_id] = datetime.now()
            guild_age = timedelta(0)
        
        if guild_age >= timedelta(days=14):
            try:
                print(f"🚪 Leaving server {guild_name} ({guild_id}) - Age: {guild_age.days} days")
                await guild.leave()
                
                main_guild = bot.get_guild(MAIN_SERVER)
                if main_guild:
                    for channel in main_guild.text_channels:
                        if channel.permissions_for(main_guild.me).send_messages:
                            embed = discord.Embed(
                                title="👋 Left Server",
                                description=f"Automatically left **{guild_name}** after 14 days.",
                                color=0xED4245,
                                timestamp=datetime.now()
                            )
                            embed.add_field(name="Server ID", value=f"`{guild_id}`", inline=True)
                            embed.add_field(name="Age", value=f"{guild_age.days} days", inline=True)
                            embed.set_footer(text="Members Grow • Auto-cleanup")
                            await channel.send(embed=embed)
                            break
                
                if guild_id in server_join_times:
                    del server_join_times[guild_id]
                    
            except Exception as e:
                print(f"❌ Error leaving server {guild_name}: {e}")
        else:
            print(f"✅ Server {guild_name} is {guild_age.days} days old - OK")

@bot.event
async def on_guild_join(guild):
    if guild.id != MAIN_SERVER:
        server_join_times[guild.id] = datetime.now()
        print(f"📝 Bot joined new server: {guild.name} ({guild.id})")
        
        main_guild = bot.get_guild(MAIN_SERVER)
        if main_guild:
            for channel in main_guild.text_channels:
                if channel.permissions_for(main_guild.me).send_messages:
                    embed = discord.Embed(
                        title="🌱 Joined New Server",
                        description=f"Bot added to **{guild.name}**",
                        color=0x57F287,
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
                    embed.add_field(name="Members", value=f"{guild.member_count}", inline=True)
                    embed.add_field(name="Auto-Leave", value="In 14 days", inline=True)
                    embed.set_footer(text="Members Grow • Tracking new server")
                    await channel.send(embed=embed)
                    break

@bot.event
async def on_guild_remove(guild):
    if guild.id in server_join_times:
        del server_join_times[guild.id]
        print(f"🗑️ Removed tracking for server: {guild.name} ({guild.id})")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Command not found. Use `!help` to see available commands.")
    else:
        print(f"❌ Command error: {error}")

def refresh_access_token(refresh_token):
    try:
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        response = requests.post('https://discord.com/api/v10/oauth2/token', data=data)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Token refresh failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Token refresh error: {e}")
        return None

def get_valid_token(user_id, access_token, refresh_token):
    headers = {'Authorization': f'Bearer {access_token}'}
    test_response = requests.get('https://discord.com/api/v10/users/@me', headers=headers)
    
    if test_response.status_code == 200:
        return access_token
    
    print(f"🔄 Token expired for user {user_id}, refreshing...")
    new_tokens = refresh_access_token(refresh_token)
    
    if new_tokens:
        update_token_in_file(user_id, new_tokens['access_token'], new_tokens['refresh_token'])
        return new_tokens['access_token']
    else:
        print(f"❌ Failed to refresh token for user {user_id}")
        return None

def update_token_in_file(user_id, new_access_token, new_refresh_token):
    try:
        if not os.path.exists('auths.txt'):
            return False
        
        with open('auths.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        updated = False
        new_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) >= 3 and parts[0] == user_id:
                new_line = f"{user_id},{new_access_token},{new_refresh_token}\n"
                new_lines.append(new_line)
                updated = True
                print(f"✅ Updated tokens for user {user_id}")
            else:
                new_lines.append(line + '\n')
        
        if updated:
            with open('auths.txt', 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            return True
        return False
    except Exception as e:
        print(f"❌ Error updating tokens in file: {e}")
        return False

@bot.hybrid_command(name='get_token')
async def get_auth_token(ctx):
    """Get authentication link"""
    try:
        redirect_url = f"{REDIRECT_BASE}/callback"
        scopes = "identify guilds.join"
        
        auth_params = {
            'client_id': CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': redirect_url,
            'scope': scopes,
            'prompt': 'consent'
        }
        
        oauth_url = f"https://discord.com/oauth2/authorize?{urlencode(auth_params)}"
        
        embed = discord.Embed(
            title="🔐 Get Your Token",
            description="Authenticate your Discord account to be added to servers automatically.",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        embed.add_field(
            name="📋 Step 1",
            value=f"[**Click here to authorize**]({oauth_url}) — grant permission to link your account.",
            inline=False
        )
        embed.add_field(
            name="✂️ Step 2",
            value="After authorizing, **copy the code** shown on the redirect page.",
            inline=False
        )
        embed.add_field(
            name="⌨️ Step 3",
            value="Run `!auth YOUR_CODE` to complete authentication.",
            inline=False
        )
        embed.add_field(
            name="⏰ Time Limit",
            value="Your code expires in **10 minutes** — act fast!",
            inline=False
        )
        embed.set_footer(text="Members Grow • Authentication")
        
        await ctx.send(embed=embed)
        print(f"✅ Sent auth link to {ctx.author.name}")
        
    except Exception as e:
        await ctx.send(f"❌ Error generating auth link: {str(e)}")
        print(f"❌ Error in get_token: {e}")

@bot.hybrid_command(name='auth')
async def authenticate_user(ctx, authorization_code: str):
    """Authenticate user with code"""
    try:
        authorization_code = authorization_code.strip()
        current_user_id = str(ctx.author.id)
        
        print(f"🔐 PROCESSING CODE: {authorization_code} for user {current_user_id}")
        
        msg = await ctx.send("🔄 Starting authentication...")
        
        token_data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code', 
            'code': authorization_code,
            'redirect_uri': f"{REDIRECT_BASE}/callback"
        }
        
        await msg.edit(content="🔄 Exchanging code for token...")
        token_response = requests.post('https://discord.com/api/v10/oauth2/token', data=token_data)
        
        if token_response.status_code != 200:
            error_info = token_response.json()
            await msg.edit(content=f"❌ Token exchange failed: {error_info.get('error_description', 'Unknown error')}")
            return
        
        token_info = token_response.json()
        access_token = token_info['access_token']
        refresh_token = token_info['refresh_token']
        
        print(f"✅ Token obtained: {access_token[:20]}...")
        
        username = ctx.author.name
        auth_entry = f"{current_user_id},{access_token},{refresh_token}\n"
        
        print(f"💾 Preparing to save: {auth_entry.strip()}")
        
        existing_entries = []
        if os.path.exists('auths.txt'):
            try:
                with open('auths.txt', 'r', encoding='utf-8') as auth_file:
                    existing_entries = auth_file.readlines()
                print(f"📖 Read {len(existing_entries)} existing entries")
            except Exception as e:
                print(f"⚠️ Error reading auth file: {e}")
                existing_entries = []
        
        cleaned_entries = []
        for line in existing_entries:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) >= 1 and parts[0] == current_user_id:
                print(f"🔄 Replacing old entry for user {current_user_id}")
                continue
            cleaned_entries.append(line + '\n')
        
        cleaned_entries.append(auth_entry)
        
        try:
            with open('auths.txt', 'w', encoding='utf-8') as auth_file:
                auth_file.writelines(cleaned_entries)
            print(f"✅ Successfully wrote {len(cleaned_entries)} entries to auths.txt")
        except Exception as e:
            print(f"❌ Error writing to auth file: {e}")
            await ctx.send(f"❌ Error saving authentication: {e}")
            return
        
        success_embed = discord.Embed(
            title="✅ Authentication Successful",
            description=f"Welcome, **{username}**! Your account is now linked and ready.",
            color=0x57F287,
            timestamp=datetime.now()
        )
        success_embed.add_field(name="🆔 Your ID", value=f"`{current_user_id}`", inline=True)
        success_embed.add_field(
            name="📌 What's Next?",
            value="You'll automatically be added to servers when an admin runs `!djoin SERVER_ID`.",
            inline=False
        )
        success_embed.set_footer(text="Members Grow • Authenticated")
        
        await msg.edit(content="", embed=success_embed)
        print(f"✅ Authentication completed for user {current_user_id}")
        
    except Exception as error:
        await ctx.send(f"❌ Error: {str(error)}")
        print(f"❌ Exception: {error}")

@bot.hybrid_command(name='djoin')
async def join_server(ctx, target_server_id: str):
    """Add ALL authenticated users to a server - WITH TOKEN REFRESH"""
    try:
        bot_in_server = False
        server_name = "Unknown"
        
        for guild in bot.guilds:
            if str(guild.id) == target_server_id:
                bot_in_server = True
                server_name = guild.name
                break
        
        if not bot_in_server:
            invite_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&permissions=8&scope=bot%20applications.commands"
            
            embed = discord.Embed(
                title="❌ Bot Not in Server",
                description=f"I'm not in the server `{target_server_id}`. Add me first, then try again.",
                color=0xED4245,
                timestamp=datetime.now()
            )
            embed.add_field(
                name="🔗 Invite Link",
                value=f"[**Click to add bot to server**]({invite_url})",
                inline=False
            )
            embed.set_footer(text="Members Grow • Missing server")
            await ctx.send(embed=embed)
            return
        
        if not os.path.exists('auths.txt'):
            await ctx.send("❌ No users are authenticated yet. Use `!get_token` to share with users.")
            return
        
        authenticated_users = []
        with open('auths.txt', 'r') as auth_file:
            for line_num, line in enumerate(auth_file, 1):
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',')
                if len(parts) >= 3:
                    user_id = parts[0]
                    access_token = parts[1]
                    refresh_token = parts[2]
                    validated_token = get_valid_token(user_id, access_token, refresh_token)
                    
                    if validated_token:
                        authenticated_users.append({
                            'line': line_num,
                            'user_id': user_id,
                            'access_token': validated_token
                        })
                    else:
                        print(f"⚠️ User {user_id} (line {line_num}) has invalid token, skipping...")
        
        total_users = len(authenticated_users)
        
        if total_users == 0:
            await ctx.send("❌ No valid authenticated users found. All tokens may be expired.")
            return
        
        embed = discord.Embed(
            title="🚀 Adding Members",
            description=f"Adding **{total_users}** authenticated members to **{server_name}**",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        embed.add_field(name="🆔 Server", value=f"`{target_server_id}`", inline=True)
        embed.add_field(name="👥 Members", value=f"{total_users}", inline=True)
        embed.add_field(name="⏳ Status", value="In progress...", inline=True)
        embed.set_footer(text="Members Grow • Adding members")
        await ctx.send(embed=embed)
        
        success_count = 0
        fail_count = 0
        failed_users = []
        
        progress_msg = await ctx.send(f"📊 Progress: 0/{total_users}")
        
        for idx, user in enumerate(authenticated_users, 1):
            user_id = user['user_id']
            valid_token = user['access_token']
            
            try:
                join_headers = {
                    'Authorization': f'Bearer {valid_token}',
                    'Content-Type': 'application/json'
                }
                
                join_response = requests.put(
                    f'https://discord.com/api/v10/guilds/{target_server_id}/members/{user_id}',
                    headers=join_headers
                )
                
                if join_response.status_code == 201 or join_response.status_code == 204:
                    success_count += 1
                elif join_response.status_code == 429:
                    retry_after = join_response.json().get('retry_after', 1)
                    print(f"⏳ Rate limited! Waiting {retry_after}s...")
                    await asyncio.sleep(retry_after + 1)
                    
                    join_response = requests.put(
                        f'https://discord.com/api/v10/guilds/{target_server_id}/members/{user_id}',
                        headers=join_headers
                    )
                    
                    if join_response.status_code == 201 or join_response.status_code == 204:
                        success_count += 1
                    else:
                        fail_count += 1
                        failed_users.append(f"{user_id} (HTTP {join_response.status_code})")
                else:
                    fail_count += 1
                    failed_users.append(f"{user_id} (HTTP {join_response.status_code})")
                    
            except Exception as e:
                fail_count += 1
                failed_users.append(f"{user_id} (Error: {str(e)[:50]})")
            
            if idx % 5 == 0 or idx == total_users:
                try:
                    await progress_msg.edit(content=f"📊 Progress: {idx}/{total_users}")
                except:
                    pass
        
        result_embed = discord.Embed(
            title="✅ Finished Adding Members",
            description=f"Results for **{server_name}**",
            color=0x57F287 if fail_count == 0 else 0xFEE75C,
            timestamp=datetime.now()
        )
        result_embed.add_field(name="✅ Added", value=str(success_count), inline=True)
        result_embed.add_field(name="❌ Failed", value=str(fail_count), inline=True)
        result_embed.add_field(name="📊 Total Attempted", value=str(total_users), inline=True)
        result_embed.set_footer(text="Members Grow • Complete")
        
        if failed_users:
            failed_list = "\n".join(failed_users[:10])
            if len(failed_users) > 10:
                failed_list += f"\n... and {len(failed_users) - 10} more"
            result_embed.add_field(name="Failed Users", value=f"```{failed_list}```", inline=False)
        
        await ctx.send(embed=result_embed)
        
    except Exception as error:
        await ctx.send(f"❌ Error: {str(error)}")
        print(f"❌ Exception in djoin: {error}")

@bot.hybrid_command(name='help')
async def help_command(ctx):
    """Show help message"""
    embed = discord.Embed(
        title="📖 Commands",
        description="**Members Grow** — Add authenticated users to any server with one command.",
        color=0x5865F2,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="🔐 `get_token`",
        value="Get an OAuth link to authenticate your Discord account.",
        inline=False
    )
    embed.add_field(
        name="✅ `auth <code>`",
        value="Complete authentication with the code from the redirect page.",
        inline=False
    )
    embed.add_field(
        name="🚀 `djoin <server_id>`",
        value="(Admin) Add all authenticated users to a server. Bot must be in that server.",
        inline=False
    )
    embed.add_field(
        name="📊 `count`",
        value="Show how many users are authenticated.",
        inline=False
    )
    embed.add_field(
        name="❓ `help`",
        value="Show this command list.",
        inline=False
    )
    
    embed.set_footer(text="Members Grow • Help")
    await ctx.send(embed=embed)

@bot.hybrid_command(name='count')
async def count_tokens(ctx):
    """Show token count"""
    try:
        if not os.path.exists('auths.txt'):
            await ctx.send("📊 **Token Count:** 0 (No authenticated users yet)")
            return
        
        count = 0
        user_ids = []
        
        with open('auths.txt', 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split(',')
                    if len(parts) >= 3:
                        count += 1
                        user_ids.append(parts[0])
        
        embed = discord.Embed(
            title="📊 Token Statistics",
            description=f"**{count}** authenticated user{'s' if count != 1 else ''} in the database.",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        embed.add_field(name="👥 Total Users", value=f"`{count}`", inline=True)
        
        if user_ids:
            id_list = "\n".join([f"`{uid}`" for uid in user_ids[:20]])
            if len(user_ids) > 20:
                id_list += f"\n... and {len(user_ids) - 20} more"
            embed.add_field(name="User IDs", value=id_list, inline=False)
        
        embed.set_footer(text="Members Grow • Statistics")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error counting tokens: {str(e)}")

# ------------------------------------------------------------
# Web server for OAuth callback and redirect page
# ------------------------------------------------------------
class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == '/callback' or parsed.path == '/':
            params = parse_qs(parsed.query)
            code = params.get('code', [None])[0]
            
            if code:
                escaped_code = html.escape(code)
                page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Authentication - Members Grow</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }}
    .card {{
      background: rgba(255, 255, 255, 0.05);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 16px;
      padding: 40px;
      max-width: 520px;
      width: 100%;
      text-align: center;
    }}
    h1 {{ color: #fff; font-size: 28px; margin-bottom: 8px; }}
    p {{ color: #a0aec0; margin-bottom: 24px; line-height: 1.6; }}
    .code-box {{
      background: rgba(0, 0, 0, 0.4);
      border: 2px solid #5865F2;
      border-radius: 12px;
      padding: 16px 20px;
      font-family: 'Courier New', monospace;
      font-size: 14px;
      color: #fff;
      word-break: break-all;
      margin-bottom: 20px;
      user-select: all;
    }}
    .btn {{
      background: #5865F2;
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 12px 28px;
      font-size: 16px;
      cursor: pointer;
      transition: background 0.2s;
    }}
    .btn:hover {{ background: #4752c4; }}
    .footer {{ margin-top: 24px; font-size: 13px; color: #4a5568; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>✅ Authorized!</h1>
    <p>Copy your authorization code below, then go back to Discord and run:<br><code style="background: rgba(88,101,242,0.2); padding: 4px 8px; border-radius: 4px; color: #fff;">!auth YOUR_CODE</code></p>
    <div class="code-box" id="code">{escaped_code}</div>
    <button class="btn" onclick="copyCode()">📋 Copy Code</button>
    <div class="footer">Members Grow • Authentication</div>
  </div>
  <script>
    function copyCode() {{
      const code = document.getElementById('code').textContent;
      navigator.clipboard.writeText(code).then(() => {{
        const btn = document.querySelector('.btn');
        btn.textContent = '✅ Copied!';
        setTimeout(() => btn.textContent = '📋 Copy Code', 2000);
      }});
    }}
  </script>
</body>
</html>"""
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(page.encode('utf-8'))
            else:
                page = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Members Grow</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }}
    .card {{
      background: rgba(255, 255, 255, 0.05);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 16px;
      padding: 40px;
      max-width: 420px;
      width: 100%;
      text-align: center;
    }}
    h1 {{ color: #fff; font-size: 24px; margin-bottom: 8px; }}
    p {{ color: #a0aec0; line-height: 1.6; }}
    .footer {{ margin-top: 24px; font-size: 13px; color: #4a5568; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>👋 Members Grow</h1>
    <p>To get started, use the <code>!get_token</code> command in Discord to receive an authorization link.</p>
    <div class="footer">Members Grow Bot</div>
  </div>
</body>
</html>"""
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(page.encode('utf-8'))
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def log_message(self, format, *args):
        print(f"🌐 [Web] {args[0]} {args[1]} {args[2]}")

def run_web_server():
    port = int(os.getenv('PORT', 5000))
    server = http.server.HTTPServer(('0.0.0.0', port), OAuthHandler)
    print(f"🌐 Web server running on port {port}")
    print(f"🌐 OAuth callback URL: {REDIRECT_BASE}/callback")
    server.serve_forever()

# Start web server in a background thread
web_thread = threading.Thread(target=run_web_server, daemon=True)
web_thread.start()
print("🚀 Web server thread started")

# Run the bot
print("\n" + "=" * 46)
print("     Members Grow Bot is online!")
print("=" * 46 + "\n")
bot.run(BOT_TOKEN)
