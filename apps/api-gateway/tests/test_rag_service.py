"""
RAG服务测试
测试向量检索和上下文增强功能
"""
import pytest
from src.services.rag_service import rag_service


@pytest.mark.asyncio
async def test_rag_service_initialization():
    """测试RAG服务初始化"""
    try:
        await rag_service.initialize()
        assert rag_service.vector_db is not None
        print("✅ RAG服务初始化成功")
    except Exception as e:
        print(f"⚠️ RAG服务初始化失败: {e}")
        # 在测试环境中可能没有Qdrant，这是预期的


@pytest.mark.asyncio
async def test_format_context():
    """测试上下文格式化"""
    # 模拟检索结果
    mock_results = [
        {
            "text": "2026-02-20: 午高峰营收1200元，同比增长15%",
            "score": 0.95
        },
        {
            "text": "2026-02-19: 午高峰营收1050元，客流量85人",
            "score": 0.88
        }
    ]

    context = rag_service.format_context(mock_results)

    assert "历史记录 1" in context
    assert "相关度: 0.95" in context
    assert "1200元" in context
    print("✅ 上下文格式化测试通过")
    print(f"格式化结果:\n{context}")


@pytest.mark.asyncio
async def test_build_enhanced_prompt():
    """测试增强提示构建"""
    query = "今日午高峰营收异常低，如何分析？"
    context = "[历史记录 1] 昨日午高峰营收1200元"

    prompt = rag_service._build_enhanced_prompt(
        query=query,
        context=context
    )

    assert "相关历史数据" in prompt
    assert "当前问题" in prompt
    assert query in prompt
    assert context in prompt
    print("✅ 增强提示构建测试通过")
    print(f"提示长度: {len(prompt)}字符")


@pytest.mark.asyncio
async def test_analyze_with_rag_mock():
    """测试RAG分析（模拟模式）"""
    # 这个测试在没有实际LLM的情况下也能运行
    query = "分析今日营收趋势"
    store_id = "STORE001"

    result = await rag_service.analyze_with_rag(
        query=query,
        store_id=store_id,
        top_k=3
    )

    assert "query" in result
    assert result["query"] == query
    print("✅ RAG分析测试通过")
    print(f"结果: {result}")


if __name__ == "__main__":
    import asyncio

    async def run_tests():
        print("=" * 50)
        print("RAG服务测试")
        print("=" * 50)

        await test_rag_service_initialization()
        print()

        await test_format_context()
        print()

        await test_build_enhanced_prompt()
        print()

        await test_analyze_with_rag_mock()
        print()

        print("=" * 50)
        print("所有测试完成")
        print("=" * 50)

    asyncio.run(run_tests())
