"""
企业微信消息加解密工具
WeChat Work Message Crypto Utility

用于企业微信回调消息的签名验证、加密和解密
"""
import hashlib
import base64
import struct
import socket
from typing import Tuple, Optional
import xml.etree.ElementTree as ET
import structlog

logger = structlog.get_logger()


class WeChatCrypto:
    """企业微信消息加解密"""

    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        """
        初始化加解密工具

        Args:
            token: 企业微信回调Token
            encoding_aes_key: 企业微信回调EncodingAESKey (43位字符)
            corp_id: 企业ID
        """
        self.token = token
        self.encoding_aes_key = encoding_aes_key
        self.corp_id = corp_id

        # EncodingAESKey是43位字符，需要补充一个'='变成44位，然后base64解码得到32字节的AES密钥
        if encoding_aes_key:
            self.aes_key = base64.b64decode(encoding_aes_key + "=")
        else:
            self.aes_key = None

    def verify_signature(
        self,
        signature: str,
        timestamp: str,
        nonce: str,
        echo_str: Optional[str] = None
    ) -> bool:
        """
        验证签名

        Args:
            signature: 签名
            timestamp: 时间戳
            nonce: 随机字符串
            echo_str: 验证URL时的加密字符串（可选）

        Returns:
            签名是否有效
        """
        try:
            # 将token、timestamp、nonce、echo_str按字典序排序
            params = [self.token, timestamp, nonce]
            if echo_str:
                params.append(echo_str)

            params.sort()

            # 拼接字符串并计算SHA1
            sign_str = "".join(params)
            calculated_signature = hashlib.sha1(sign_str.encode()).hexdigest()

            # 比较签名
            is_valid = calculated_signature == signature

            if not is_valid:
                logger.warning(
                    "企业微信签名验证失败",
                    expected=signature,
                    calculated=calculated_signature
                )

            return is_valid

        except Exception as e:
            logger.error("签名验证异常", error=str(e), exc_info=e)
            return False

    def decrypt_message(self, encrypt_msg: str) -> Tuple[Optional[str], Optional[str]]:
        """
        解密消息

        Args:
            encrypt_msg: 加密的消息内容

        Returns:
            (解密后的消息, 错误信息)
        """
        try:
            if not self.aes_key:
                return None, "EncodingAESKey未配置"

            # 使用pycryptodome进行AES解密
            try:
                from Crypto.Cipher import AES
            except ImportError:
                logger.error("缺少pycryptodome库，无法解密消息")
                return None, "缺少pycryptodome库"

            # Base64解码
            cipher_text = base64.b64decode(encrypt_msg)

            # AES解密
            cipher = AES.new(self.aes_key, AES.MODE_CBC, self.aes_key[:16])
            decrypted = cipher.decrypt(cipher_text)

            # 去除补位字符
            pad = decrypted[-1]
            if isinstance(pad, str):
                pad = ord(pad)
            decrypted = decrypted[:-pad]

            # 解析消息内容
            # 格式：16字节随机字符串 + 4字节消息长度 + 消息内容 + corp_id
            content = decrypted[16:]
            msg_len = struct.unpack("!I", content[:4])[0]
            msg_content = content[4:4 + msg_len].decode("utf-8")
            from_corp_id = content[4 + msg_len:].decode("utf-8")

            # 验证corp_id
            if from_corp_id != self.corp_id:
                logger.warning(
                    "企业ID不匹配",
                    expected=self.corp_id,
                    received=from_corp_id
                )
                return None, "企业ID不匹配"

            return msg_content, None

        except Exception as e:
            logger.error("消息解密失败", error=str(e), exc_info=e)
            return None, str(e)

    def encrypt_message(self, msg_content: str, nonce: str) -> Tuple[Optional[str], Optional[str]]:
        """
        加密消息

        Args:
            msg_content: 要加密的消息内容
            nonce: 随机字符串

        Returns:
            (加密后的消息, 错误信息)
        """
        try:
            if not self.aes_key:
                return None, "EncodingAESKey未配置"

            try:
                from Crypto.Cipher import AES
                from Crypto.Random import get_random_bytes
            except ImportError:
                logger.error("缺少pycryptodome库，无法加密消息")
                return None, "缺少pycryptodome库"

            # 生成16字节随机字符串
            random_str = get_random_bytes(16)

            # 消息内容转字节
            msg_bytes = msg_content.encode("utf-8")
            msg_len = struct.pack("!I", len(msg_bytes))

            # 拼接：随机字符串 + 消息长度 + 消息内容 + corp_id
            corp_id_bytes = self.corp_id.encode("utf-8")
            plain_text = random_str + msg_len + msg_bytes + corp_id_bytes

            # PKCS7补位
            block_size = 32
            padding_len = block_size - (len(plain_text) % block_size)
            padding = bytes([padding_len] * padding_len)
            plain_text += padding

            # AES加密
            cipher = AES.new(self.aes_key, AES.MODE_CBC, self.aes_key[:16])
            cipher_text = cipher.encrypt(plain_text)

            # Base64编码
            encrypted_msg = base64.b64encode(cipher_text).decode("utf-8")

            return encrypted_msg, None

        except Exception as e:
            logger.error("消息加密失败", error=str(e), exc_info=e)
            return None, str(e)

    def parse_xml_message(self, xml_data: bytes) -> Optional[dict]:
        """
        解析XML消息

        Args:
            xml_data: XML格式的消息数据

        Returns:
            解析后的消息字典
        """
        try:
            root = ET.fromstring(xml_data)
            message = {}

            for child in root:
                message[child.tag] = child.text

            return message

        except Exception as e:
            logger.error("XML解析失败", error=str(e), exc_info=e)
            return None

    def generate_response_xml(
        self,
        encrypt_msg: str,
        timestamp: str,
        nonce: str
    ) -> str:
        """
        生成响应XML

        Args:
            encrypt_msg: 加密的消息内容
            timestamp: 时间戳
            nonce: 随机字符串

        Returns:
            XML格式的响应
        """
        # 计算签名
        params = [self.token, timestamp, nonce, encrypt_msg]
        params.sort()
        sign_str = "".join(params)
        signature = hashlib.sha1(sign_str.encode()).hexdigest()

        # 生成XML
        xml_template = """<xml>
<Encrypt><![CDATA[{encrypt}]]></Encrypt>
<MsgSignature><![CDATA[{signature}]]></MsgSignature>
<TimeStamp>{timestamp}</TimeStamp>
<Nonce><![CDATA[{nonce}]]></Nonce>
</xml>"""

        return xml_template.format(
            encrypt=encrypt_msg,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce
        )
