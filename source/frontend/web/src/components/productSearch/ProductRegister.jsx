import React, { Component } from 'react';
import {
  Button, Input, FileInput, SpaceBetween, Container, Header,
  FormField, Textarea, Alert, Spinner
} from '@cloudscape-design/components';
import { FetchPost } from '../../resources/data-provider';

class ProductRegister extends Component {
  constructor(props) {
    super(props);
    this.state = {
      productCode: '',
      productName: '',
      category: '',
      price: '',
      textContent: '',
      imageFile: null,
      imagePreview: null,
      loading: false,
      alert: null,
    };
  }

  handleRegister = async () => {
    const { productCode, productName, category, price, textContent, imageFile } = this.state;
    if (!productCode) {
      this.setState({ alert: { type: 'error', message: '商品コードは必須です' } });
      return;
    }

    this.setState({ loading: true, alert: null });

    let imageBase64 = '';
    let imageFormat = 'jpeg';
    if (imageFile) {
      const reader = new FileReader();
      imageBase64 = await new Promise((resolve) => {
        reader.onload = (e) => resolve(e.target.result.split(',')[1]);
        reader.readAsDataURL(imageFile);
      });
      imageFormat = imageFile.type.split('/')[1] || 'jpeg';
    }

    try {
      const response = await FetchPost('/products/register', {
        product_code: productCode,
        product_name: productName,
        category: category,
        price: parseInt(price) || 0,
        text_content: textContent,
        image_base64: imageBase64,
        image_format: imageFormat,
      }, 'ProductService');

      const body = response?.body || response;
      this.setState({
        alert: { type: 'success', message: `商品 ${productCode} を登録しました (ID: ${body?.product_id})` },
        productCode: '', productName: '', category: '', price: '', textContent: '',
        imageFile: null, imagePreview: null,
      });
    } catch (e) {
      this.setState({ alert: { type: 'error', message: `登録エラー: ${e.message}` } });
    } finally {
      this.setState({ loading: false });
    }
  };

  handleImageSelect = (files) => {
    const file = files[0];
    if (!file) return;
    this.setState({ imageFile: file });
    const reader = new FileReader();
    reader.onload = (e) => this.setState({ imagePreview: e.target.result });
    reader.readAsDataURL(file);
  };

  render() {
    const { productCode, productName, category, price, textContent, imagePreview, loading, alert } = this.state;

    return (
      <Container header={<Header variant="h2">商品登録（単品）</Header>}>
        <SpaceBetween size="m">
          {alert && <Alert type={alert.type}>{alert.message}</Alert>}

          <FormField label="商品コード *">
            <Input value={productCode} onChange={({ detail }) => this.setState({ productCode: detail.value })} placeholder="A00001" />
          </FormField>
          <FormField label="商品名">
            <Input value={productName} onChange={({ detail }) => this.setState({ productName: detail.value })} placeholder="やわらかボストンバッグ" />
          </FormField>
          <div style={{ display: 'flex', gap: '12px' }}>
            <FormField label="カテゴリ" stretch>
              <Input value={category} onChange={({ detail }) => this.setState({ category: detail.value })} placeholder="バッグ" />
            </FormField>
            <FormField label="価格">
              <Input value={price} onChange={({ detail }) => this.setState({ price: detail.value })} placeholder="3900" type="number" />
            </FormField>
          </div>
          <FormField label="商品テキスト情報">
            <Textarea value={textContent} onChange={({ detail }) => this.setState({ textContent: detail.value })}
              placeholder="◆キャッチコピー・商品説明&#10;旅行好きプランナーが作った..." rows={8} />
          </FormField>
          <FormField label="商品画像">
            <FileInput
              accept="image/*"
              value={this.state.imageFile ? [this.state.imageFile] : []}
              onChange={({ detail }) => this.handleImageSelect(detail.value)}
            >画像を選択</FileInput>
          </FormField>
          {imagePreview && <img src={imagePreview} alt="preview" style={{ maxHeight: 150, borderRadius: 4 }} />}

          <Button variant="primary" onClick={this.handleRegister} loading={loading}>登録</Button>
        </SpaceBetween>
      </Container>
    );
  }
}

export default ProductRegister;
