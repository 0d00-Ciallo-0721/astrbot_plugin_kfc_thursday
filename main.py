from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.api.event.filter import PlatformAdapterType
import datetime
import asyncio
import json
import random
import os
import time

@register(
    "astrbot_plugin_kfc_thursday",
    "和泉智宏",
    "疯狂星期四",
    "1.1",
    "https://github.com/0d00-Ciallo-0721/astrbot_plugin_kfc_thursday",
)
class KFCThursdayPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 从配置文件加载配置
        self.enabled_groups = config.get("enabled_groups", [])
        
        # 时间点及对应的提示词
        self.time_prompts = {
            "10:00": config.get("morning_prompt", "请你以撒娇的语气，写一段请求对方转账50元的消息。你非常想吃KFC，而今天是疯狂星期四，特地想用可爱的方式让对方给你转账。。"),
            "12:00": config.get("noon_prompt", "请你以可怜的语气，写一段请求对方转账50元的消息。你特别想吃KFC，但钱包空空，今天又是疯狂星期四，希望通过可怜的方式让对方转账。"),
            "18:00": config.get("evening_prompt", "你以搞笑的语气，写一段请求对方转账50元的消息。你特别想吃KFC，而今天是疯狂星期四，用幽默风趣的方式让对方给你转账。"),
            "20:00": config.get("night_prompt", "请你以卖萌的语气，写一段请求对方转账50元的消息。你超级想吃KFC，今天是疯狂星期四，用萌萌的语气请求对方转账。")
        }
        
        # 收款码图片路径
        self.payment_qrcode_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "收款码.jpg")
        if not os.path.exists(self.payment_qrcode_path):
            logger.warning(f"收款码图片不存在: {self.payment_qrcode_path}")
        
        # 检查是否需要启动定时任务
        self.check_and_start_scheduler()
        
        # 创建日常检查任务
        asyncio.create_task(self.daily_scheduler())

        logger.info("KFC星期四插件已初始化完成！")

    def check_and_start_scheduler(self):
        """检查是否需要启动定时任务"""
        now = datetime.datetime.now()
        current_weekday = now.weekday()  # 0-6，0表示周一
        
        # 检查自定义时间设置是否有今天的任务
        custom_times = self.config.get("custom_times", {})
        custom_weekday = custom_times.get("weekday", 4) - 1  # 转为0-6
        
        # 如果今天是星期四或是自定义的日期，启动定时任务
        if current_weekday == 3 or current_weekday == custom_weekday:
            logger.info(f"今天是星期{current_weekday + 1}，{'是星期四' if current_weekday == 3 else '匹配自定义日期'}，启动KFC活动定时任务")
            asyncio.create_task(self.schedule_kfc_posts())
        else:
            logger.info(f"今天是星期{current_weekday + 1}，不需要启动KFC活动定时任务")
            # 计算到下一个可能有任务的日期
            next_task_days = 7  # 默认一周后再检查
            
            # 计算到星期四的天数
            days_to_thursday = (3 - current_weekday) % 7
            if days_to_thursday == 0:  # 如果今天是星期四但已经错过了时间
                days_to_thursday = 7
                
            # 计算到自定义日期的天数
            days_to_custom = (custom_weekday - current_weekday) % 7
            if days_to_custom == 0:  # 如果今天是自定义日期但已经错过了时间
                days_to_custom = 7
                
            # 取最小值
            next_task_days = min(days_to_thursday, days_to_custom)
            
            next_check = now + datetime.timedelta(days=next_task_days)
            next_check = next_check.replace(hour=0, minute=0, second=0, microsecond=0)
            
            seconds_until_next_check = (next_check - now).total_seconds()
            logger.info(f"将在{next_task_days}天后（{next_check.strftime('%Y-%m-%d')}）检查并启动KFC活动")
            
            # 设置定时器，到下一个可能有任务的日期时再次检查
            asyncio.create_task(self.wait_for_next_check(seconds_until_next_check))

    async def daily_scheduler(self):
        """每天凌晨检查是否需要启动任务"""
        while True:
            # 计算到下一个凌晨的时间
            now = datetime.datetime.now()
            tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
            sleep_seconds = (tomorrow - now).total_seconds()
            
            # 等到凌晨
            await asyncio.sleep(sleep_seconds)
            
            # 检查是否需要启动任务
            self.check_and_start_scheduler()

    async def wait_for_next_check(self, seconds):
        """等待到下一个检查日期"""
        await asyncio.sleep(seconds)
        self.check_and_start_scheduler()

    async def schedule_kfc_posts(self):
        """定时任务，在指定时间发送KFC文案"""
        # 创建锁文件路径
        lock_file_path = os.path.join(os.path.dirname(__file__), "kfc_sending.lock")
        processed_file_path = os.path.join(os.path.dirname(__file__), "processed_times.txt")
        
        # 加载已处理的时间点
        processed_times = set()
        if os.path.exists(processed_file_path):
            try:
                with open(processed_file_path, "r") as f:
                    processed_times = set(line.strip() for line in f.readlines())
            except:
                pass
        
        while True:
            try:
                # 检查锁文件是否存在
                if os.path.exists(lock_file_path):
                    # 如果锁文件存在，检查是否过期（超过3分钟判定为过期）
                    lock_time = os.path.getmtime(lock_file_path)
                    if time.time() - lock_time < 180:  # 3分钟锁
                        # 锁未过期，等待
                        await asyncio.sleep(60)
                        continue
                    else:
                        # 锁过期，删除
                        try:
                            os.remove(lock_file_path)
                        except:
                            pass
                
                # 获取当前时间
                now = datetime.datetime.now()
                today_str = now.strftime("%Y-%m-%d")
                current_weekday = now.weekday()
                current_hour = now.hour
                current_minute = now.minute
                
                # 时间标识
                time_key = f"{today_str}_{current_hour:02d}:{current_minute:02d}"
                
                # 如果已处理过这个时间点，跳过
                if time_key in processed_times:
                    await asyncio.sleep(60)
                    continue
                
                # 检查是否是发送时间点
                should_send = False
                prompt_to_use = None
                
                # 自定义时间检查
                custom_times = self.config.get("custom_times", {})
                custom_enabled = custom_times.get("enabled", True)
                custom_weekday = custom_times.get("weekday", 4) - 1
                custom_hour = custom_times.get("hour", 18) 
                custom_minute = custom_times.get("minute", 30)
                
                if (custom_enabled and 
                    current_weekday == custom_weekday and 
                    current_hour == custom_hour and 
                    current_minute == custom_minute):
                    
                    should_send = True
                    prompt_to_use = custom_times.get("prompt", "请以你的风格写一段吸引人的KFC推销文案。")
                    logger.info(f"自定义时间点匹配: 星期{current_weekday + 1} {current_hour:02d}:{current_minute:02d}")
                
                # 检查星期四预设时间
                time_str = f"{current_hour:02d}:{current_minute:02d}"
                if current_weekday == 3 and time_str in self.time_prompts:
                    # 检查时间点是否启用
                    is_enabled = False
                    if time_str == "10:00":
                        is_enabled = self.config.get("morning_enabled", True)
                    elif time_str == "12:00":
                        is_enabled = self.config.get("noon_enabled", True)
                    elif time_str == "18:00":
                        is_enabled = self.config.get("evening_enabled", True)
                    elif time_str == "20:00":
                        is_enabled = self.config.get("night_enabled", True)
                    
                    if is_enabled:
                        should_send = True
                        prompt_to_use = self.time_prompts[time_str]
                        logger.info(f"预设时间点匹配: 星期四 {time_str}")
                
                # 如果需要发送
                if should_send and prompt_to_use:
                    # 创建锁文件
                    try:
                        with open(lock_file_path, "w") as f:
                            f.write(f"KFC sending at {time_key}")
                        
                        # 记录此时间点已处理
                        processed_times.add(time_key)
                        with open(processed_file_path, "a") as f:
                            f.write(f"{time_key}\n")
                        
                        logger.info(f"创建锁文件，开始发送KFC文案")
                        
                        # 导入消息组件
                        from astrbot.api.message_components import Plain, Image
                        
                        # 发送逻辑
                        for group_id in self.enabled_groups:
                            try:
                                # 获取KFC文案
                                kfc_text = await self.get_llm_kfc_content(prompt_to_use, group_id)
                                
                                # 找到aiocqhttp平台
                                platform = None
                                for p in self.context.platform_manager.get_insts():
                                    if p.meta().name == "aiocqhttp":
                                        platform = p
                                        break
                                
                                if platform:
                                    # 直接通过平台API发送消息
                                    client = platform.get_client()
                                    
                                    # 发送文本消息
                                    await client.send_group_msg(
                                        group_id=int(group_id), 
                                        message=kfc_text
                                    )
                                    # 在发送图片前添加日志
                                    logger.info(f"收款码图片路径: {self.payment_qrcode_path}")
                                    logger.info(f"收款码图片是否存在: {os.path.exists(self.payment_qrcode_path)}")

                                    # 发送图片
                                    if os.path.exists(self.payment_qrcode_path):
                                        try:
                                            # 方法1: 使用CQ码的file协议，需要绝对路径
                                            absolute_path = os.path.abspath(self.payment_qrcode_path)
                                            await client.send_group_msg(
                                                group_id=int(group_id),
                                                message=f"[CQ:image,file=file:///{absolute_path}]"
                                            )
                                        except Exception as e1:
                                            logger.error(f"方法1发送图片失败: {e1}")
                                            try:
                                                # 方法2: 使用base64编码发送
                                                with open(self.payment_qrcode_path, 'rb') as f:
                                                    import base64
                                                    img_base64 = base64.b64encode(f.read()).decode()
                                                    await client.send_group_msg(
                                                        group_id=int(group_id),
                                                        message=f"[CQ:image,file=base64://{img_base64}]"
                                                    )
                                            except Exception as e2:
                                                logger.error(f"方法2发送图片失败: {e2}")

                                    
                                    logger.info(f"成功发送KFC文案到群 {group_id}")
                                else:
                                    logger.error("无法获取AIOCQHTTP平台")
                                
                                await asyncio.sleep(2)
                            except Exception as e:
                                logger.error(f"发送失败: {e}")
                        
                        # 发送完成，删除锁文件
                        try:
                            os.remove(lock_file_path)
                            logger.info("文案发送完成，锁文件已删除")
                        except:
                            pass
                        
                        # 等待到下一分钟
                        next_minute = now.replace(second=0) + datetime.timedelta(minutes=1)
                        wait_seconds = (next_minute - datetime.datetime.now()).total_seconds() + 5
                        await asyncio.sleep(max(30, wait_seconds))
                    except Exception as e:
                        logger.error(f"处理KFC发送时出错: {e}")
                        # 确保锁文件被删除
                        try:
                            os.remove(lock_file_path)
                        except:
                            pass
                else:
                    # 不需要发送，等待
                    await asyncio.sleep(10)
                
                # 午夜清理过期记录
                if current_hour == 0 and current_minute == 0:
                    processed_times = set(t for t in processed_times if today_str in t)
                    with open(processed_file_path, "w") as f:
                        for t in processed_times:
                            f.write(f"{t}\n")
                
                # 继续等待检查
                await asyncio.sleep(10)
                    
            except Exception as e:
                logger.error(f"定时任务出错: {e}")
                await asyncio.sleep(60)
                # 确保锁文件被删除
                try:
                    if os.path.exists(lock_file_path):
                        os.remove(lock_file_path)
                except:
                    pass


    async def get_llm_kfc_content(self, prompt_template: str, group_id: str) -> str:
        """调用LLM生成KFC文案"""
        try:
            # 构建一个虚拟的消息会话标识符
            unified_msg_origin = f"aiocqhttp:GROUP_MESSAGE:{group_id}"
            
            # 尝试获取当前会话ID
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(unified_msg_origin)
            
            # 如果没有会话ID，创建一个新的
            if not curr_cid:
                curr_cid = await self.context.conversation_manager.new_conversation(unified_msg_origin)
                
            # 获取会话
            conversation = await self.context.conversation_manager.get_conversation(unified_msg_origin, curr_cid)
            contexts = json.loads(conversation.history) if conversation.history else []
            
            # 获取当前提供商
            provider = self.context.get_using_provider()
            if not provider:
                return "KFC疯狂星期四，炸鸡疯狂8.8折，快来KFC享用美味吧！"
                
            # 获取当前人格设置
            personality = provider.curr_personality
            personality_prompt = personality["prompt"] if personality and "prompt" in personality else ""
            
            # 调用LLM
            llm_response = await provider.text_chat(
                prompt=prompt_template,
                system_prompt=personality_prompt,
                contexts=contexts,
            )
            
            return llm_response.completion_text
            
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return "KFC疯狂星期四，V我50，请速速行动！🍗"
    
    @filter.command("kfc")
    async def kfc_command(self, event: AstrMessageEvent):
        """测试命令，立即生成一条KFC文案"""
        # 检查是否是星期四
        now = datetime.datetime.now()
        if now.weekday() != 3:  # 星期四的索引是3
            yield event.plain_result(f"今天是星期{now.weekday() + 1}，不是星期四，KFC星期四活动尚未开始。")
            return
            
        # 检查是否在启用的群列表中
        group_id = event.get_group_id()
        if not group_id or str(group_id) not in [str(g) for g in self.enabled_groups]:
            yield event.plain_result("此群未启用KFC星期四活动。")
            return
            
        # 随机选择一个提示词
        prompt = random.choice(list(self.time_prompts.values()))
        
        # 获取LLM生成的文案
        kfc_text = await self.get_llm_kfc_content(prompt, group_id)
        
        # 创建包含图片和文本的消息链
        from astrbot.api.message_components import Plain, Image
        chain = [Plain(text=kfc_text)]
        
        # 如果存在收款码图片，则添加到消息链中
        if os.path.exists(self.payment_qrcode_path):
            chain.append(Image.fromFileSystem(self.payment_qrcode_path))
        
        # 一次性发送整个消息链
        yield event.chain_result(chain)
        
    @filter.command("kfc_test")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def kfc_test(self, event: AstrMessageEvent, weekday: int = None, hour: int = None, minute: int = None):
        """测试KFC文案发送功能
        参数:
            weekday: 星期几(1-7)，默认为当前星期
            hour: 小时(0-23)，默认为当前小时
            minute: 分钟(0-59)，默认为当前分钟
        """
        # 获取当前时间，或使用用户提供的时间
        now = datetime.datetime.now()
        
        if weekday is not None:
            # 确保weekday在1-7范围内
            weekday = max(1, min(7, weekday))
            # 转换为0-6的范围(周一为0，周日为6)
            weekday = (weekday % 7) - 1
        else:
            weekday = now.weekday()
        
        hour = hour if hour is not None else now.hour
        minute = minute if minute is not None else now.minute
        
        # 格式化时间字符串
        time_str = f"{hour:02d}:{minute:02d}"
        
        # 获取群组ID
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("请在群聊中使用此命令")
            return
        
        # 使用自定义时间和星期
        custom_prompt = self.config.get("custom_prompt", "今天是KFC疯狂星期X，请你写一段有创意的肯德基推销文案，让人们想要购买肯德基。")
        custom_prompt = custom_prompt.replace("X", str(weekday + 1))  # 替换X为实际星期几
        
        # 获取LLM生成的文案
        kfc_text = await self.get_llm_kfc_content(custom_prompt, group_id)
        
        # 创建包含图片和文本的消息链
        from astrbot.api.message_components import Plain, Image
        chain = [Plain(text=f"星期{weekday + 1} {time_str}\n{kfc_text}")]
        
        # 如果存在收款码图片，则添加到消息链中
        if os.path.exists(self.payment_qrcode_path):
            chain.append(Image.fromFileSystem(self.payment_qrcode_path))
        
        # 一次性发送整个消息链
        yield event.chain_result(chain)
        
    @filter.command("kfc_status")
    async def kfc_status(self, event: AstrMessageEvent):
        """查看KFC插件状态"""
        now = datetime.datetime.now()
        is_thursday = now.weekday() == 3
        
        if not is_thursday:
            days_until_thursday = (3 - now.weekday()) % 7
            next_thursday = now + datetime.timedelta(days=days_until_thursday)
            next_thursday_str = next_thursday.strftime("%Y-%m-%d")
        
        status_text = f"KFC星期四插件状态:\n"
        status_text += f"今天是: 星期{now.weekday() + 1}\n"
        status_text += f"是否星期四: {'是' if is_thursday else '否'}\n"
        
        if not is_thursday:
            status_text += f"距离下一个星期四: {days_until_thursday}天 ({next_thursday_str})\n"
        
        status_text += f"已启用群组数: {len(self.enabled_groups)}\n"
        status_text += f"群组列表: {', '.join(self.enabled_groups) if self.enabled_groups else '无'}\n"
        
        # 显示时间点及其状态
        status_text += "发送时间点状态:\n"
        status_text += f"- 10:00: {'启用' if self.config.get('morning_enabled', True) else '禁用'}\n"
        status_text += f"- 12:00: {'启用' if self.config.get('noon_enabled', True) else '禁用'}\n"
        status_text += f"- 18:00: {'启用' if self.config.get('evening_enabled', True) else '禁用'}\n"
        status_text += f"- 20:00: {'启用' if self.config.get('night_enabled', True) else '禁用'}\n"
        
        # 显示自定义时间点
        custom_times = self.config.get("custom_times", {})
        if custom_times:
            weekday = custom_times.get("weekday", 4)
            hour = custom_times.get("hour", 18)
            minute = custom_times.get("minute", 30)
            custom_enabled = custom_times.get("enabled", True)
            status_text += f"自定义时间点:\n"
            status_text += f"- 状态: {'启用' if custom_enabled else '禁用'}\n"
            status_text += f"- 时间: 星期{weekday} {hour:02d}:{minute:02d}\n"
        
        status_text += f"收款码图片: {'存在' if os.path.exists(self.payment_qrcode_path) else '不存在'}"
        
        yield event.plain_result(status_text)
